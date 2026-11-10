import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useLang } from '../i18n/LangContext';
import { arenaSocketUrl } from '../lib/api';
import { useAuth } from '../auth/AuthContext';
import { FlameIcon, SwordsIcon, TrophyIcon } from '../components/icons';
import { Check, Link as LinkIcon, Send } from 'lucide-react';
import confetti from 'canvas-confetti';
import {
  arenaOpponentRows,
  arenaRowOf,
  arenaScoreOf,
  normalizeArenaScores,
} from '../lib/essays-arena';
import type { ArenaScoreRow } from '../lib/essays-arena';

/**
 * Duel room — real-time 1v1 quiz duel over Django Channels.
 *
 * Auth: the WS consumer authenticates via SimpleJWT access token in query string
 * or header; close code 4001 means "not logged in".
 *
 * Protocol (apps/arena/consumers.py + templates/arena/duel_room.html):
 *   → join_room {room_code} · submit_answer {room_code, answer, question_index}
 *     · leave_room
 *   ← connected {user_id} · room_joined {player1, player2, total_questions,
 *     time_per_question, current_question_index, is_bot_duel, status} ·
 *     match_found {room_code, player1, player2, total_questions} ·
 *     queue_update {message, position} · send_question {question_index,
 *     question{question_text, option_a..d, points}, time_limit} ·
 *     answer_result {is_correct, points, base_points, combo_bonus,
 *     time_bonus, correct_answer, streak} · live_score_update {scores[],
 *     answered_by} (scores is a LIST — see services.get_scores) ·
 *     game_over {winner, winner_id, scores[], mode} · error {message}
 *
 * The correct answer is NEVER in send_question — reveal comes only from
 * answer_result. Server timer is authoritative; expiry only locks the
 * options locally. Reconnect mirrors the legacy page (retry after 3s).
 */

type State =
  | 'session'
  | 'connecting'
  | 'waiting'
  | 'countdown'
  | 'playing'
  | 'gameover'
  | 'error';

interface DuelPlayer {
  id: number | null;
  name: string;
  is_bot?: boolean;
}

interface Question {
  question_text: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  points: number;
}

const OPTS = ['a', 'b', 'c', 'd'] as const;
const COUNTDOWN_FROM = 3;
const BACKOFF_DELAYS = [1000, 2000, 5000];
const MAX_RECONNECTS = 8;

export default function DuelRoom() {
  const { code = '' } = useParams();
  const navigate = useNavigate();
  const { t } = useLang();
  const { user, loading: authLoading } = useAuth();

  const [state, setState] = useState<State>('session');
  const [notice, setNotice] = useState('');
  const [question, setQuestion] = useState<Question | null>(null);
  const [qIndex, setQIndex] = useState(0);
  const [total, setTotal] = useState(10);
  const [timeLeft, setTimeLeft] = useState(15);
  // per-question limit from the server (kept for reset/progress; timeLeft drives the countdown)
  const [, setTimeLimit] = useState(15);
  const [rows, setRows] = useState<ArenaScoreRow[]>([]);
  const [myId, setMyId] = useState<number | null>(null);
  const [p1, setP1] = useState<DuelPlayer | null>(null);
  const [p2, setP2] = useState<DuelPlayer | null>(null);
  const [isBotDuel, setIsBotDuel] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [reveal, setReveal] = useState<string | null>(null);
  const [gained, setGained] = useState<number | null>(null);
  const [streak, setStreak] = useState(0);
  const [disabled, setDisabled] = useState(false);
  const [opponentAnswered, setOpponentAnswered] = useState(false);
  const [countdown, setCountdown] = useState(COUNTDOWN_FROM);
  const [result, setResult] = useState<'win' | 'lose' | 'draw' | ''>('');
  const [rewards, setRewards] = useState({ xp: 0, coins: 0, elo: 0 });
  const [opponentDisconnected, setOpponentDisconnected] = useState(false);
  const [opponentGraceSeconds, setOpponentGraceSeconds] = useState(30);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyInviteLink = async () => {
    const url = `${window.location.origin}/arena/${code}`;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      /* fallback */
    }
  };

  const ws = useRef<WebSocket | null>(null);
  const stateRef = useRef<State>('session');
  const myIdRef = useRef<number | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const attempts = useRef(0);
  const left = useRef(false);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const missedPongs = useRef(0);
  stateRef.current = state;

  const clearTimers = () => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    if (countdownTimer.current) clearInterval(countdownTimer.current);
    if (pingTimer.current) clearInterval(pingTimer.current);
    reconnectTimer.current = null;
    countdownTimer.current = null;
  };

  const applyPlayers = useCallback(
    (a: unknown, b: unknown, totalQ?: unknown, botDuel?: unknown) => {
      const norm = (p: unknown): DuelPlayer | null => {
        if (!p || typeof p !== 'object') return null;
        const o = p as Record<string, unknown>;
        return {
          id: o.id === null || o.id === undefined ? null : Number(o.id),
          name: String(o.name ?? '?'),
          is_bot: o.is_bot === true,
        };
      };
      setP1(norm(a));
      setP2(norm(b));
      if (totalQ !== undefined) setTotal(Number(totalQ) || 10);
      if (botDuel !== undefined) setIsBotDuel(botDuel === true);
    },
    [],
  );

  const handleMessage = useCallback(
    (msg: Record<string, unknown>) => {
      switch (msg.type) {
        case 'connected':
          setMyId(Number(msg.user_id));
          myIdRef.current = Number(msg.user_id);
          break;
        case 'pong':
          missedPongs.current = 0;
          break;
        case 'opponent_disconnected':
          setOpponentDisconnected(true);
          setOpponentGraceSeconds(Number(msg.grace_period || 30));
          break;
        case 'opponent_reconnected':
          setOpponentDisconnected(false);
          break;
        case 'room_joined':
          applyPlayers(
            msg.player1,
            msg.player2,
            msg.total_questions,
            msg.is_bot_duel,
          );
          if (msg.time_per_question !== undefined) {
            setTimeLimit(Number(msg.time_per_question) || 15);
          }
          if (msg.current_question_index !== undefined) {
            setQIndex(Number(msg.current_question_index) || 0);
          }
          setState('waiting');
          setNotice(String(msg.message ?? t('arena_wait_hint')));
          break;
        case 'match_found':
          applyPlayers(msg.player1, msg.player2, msg.total_questions);
          if (countdownTimer.current) clearInterval(countdownTimer.current);
          setCountdown(COUNTDOWN_FROM);
          setState('countdown');
          countdownTimer.current = setInterval(() => {
            setCountdown((c) => {
              if (c <= 1 && countdownTimer.current) {
                clearInterval(countdownTimer.current);
                countdownTimer.current = null;
              }
              return c - 1;
            });
          }, 1000);
          break;
        case 'queue_update':
          setNotice(String(msg.message ?? ''));
          break;
        case 'send_question': {
          const q = msg.question as Question;
          setQuestion(q);
          setQIndex(Number(msg.question_index ?? 0));
          const limit = Number(msg.time_limit ?? 15);
          setTimeLimit(limit);
          setTimeLeft(limit);
          setPicked(null);
          setReveal(null);
          setGained(null);
          setDisabled(false);
          setOpponentAnswered(false);
          setState('playing');
          break;
        }
        case 'answer_result':
          setReveal(String(msg.correct_answer ?? ''));
          setStreak(Number(msg.streak ?? 0));
          setGained(Number(msg.points ?? 0));
          break;
        case 'live_score_update': {
          const list = normalizeArenaScores(msg.scores);
          setRows(list);
          const me = arenaRowOf(list, myIdRef.current);
          if (me?.streak !== undefined) setStreak(me.streak);
          if (
            msg.answered_by !== undefined &&
            Number(msg.answered_by) !== myIdRef.current
          ) {
            setOpponentAnswered(true);
          }
          break;
        }
        case 'game_over': {
          const list = normalizeArenaScores(msg.scores);
          setRows(list);
          const me = arenaRowOf(list, myIdRef.current);
          setRewards({
            xp: Number(me?.xp_earned ?? 0),
            coins: Number(me?.coins_earned ?? 0),
            elo: Number(me?.rating_change ?? 0),
          });
          const winnerId =
            msg.winner_id === null || msg.winner_id === undefined
              ? null
              : Number(msg.winner_id);
          if (winnerId === null || String(msg.winner ?? '') === 'Durang') {
            setResult('draw');
          } else if (winnerId === myIdRef.current) {
            setResult('win');
            try {
              confetti({
                particleCount: 80,
                spread: 80,
                origin: { y: 0.55 },
                colors: ['#F59E0B', '#10B981', '#FBBF24', '#34D399', '#8B5CF6'],
              });
            } catch {
              /* ignore */
            }
          } else {
            setResult('lose');
          }
          if (countdownTimer.current) clearInterval(countdownTimer.current);
          setOpponentDisconnected(false);
          setState('gameover');
          break;
        }
        case 'error':
          setNotice(String(msg.message ?? 'Error'));
          break;
        case 'left_room':
          left.current = true;
          navigate('/arena');
          break;
        default:
          break;
      }
    },
    [applyPlayers, navigate, t],
  );

  const connect = useCallback(() => {
    if (left.current) return;
    if (stateRef.current === 'gameover' || stateRef.current === 'error') return;
    setState('connecting');
    const sock = new WebSocket(arenaSocketUrl(code));
    ws.current = sock;
    sock.onopen = () => {
      attempts.current = 0;
      setIsReconnecting(false);
      missedPongs.current = 0;
      if (stateRef.current !== 'playing') {
        setState('waiting');
      }
      setNotice(t('arena_wait_hint'));
      sock.send(JSON.stringify({ type: 'join_room', room_code: code }));
    };
    sock.onmessage = (e: MessageEvent) => {
      try {
        handleMessage(JSON.parse(String(e.data)) as Record<string, unknown>);
      } catch {
        /* malformed frame — ignore */
      }
    };
    sock.onerror = () => {
      // onclose follows with the detail; nothing to do here.
    };
    sock.onclose = (ev) => {
      ws.current = null;
      if (left.current || stateRef.current === 'gameover') return;
      if (ev.code === 4001) {
        setState('error');
        setNotice(t('arena_login_needed'));
        return;
      }
      if (attempts.current >= MAX_RECONNECTS) {
        setState('error');
        setNotice(t('arena_ws_error'));
        setIsReconnecting(false);
        return;
      }
      const delay = BACKOFF_DELAYS[Math.min(attempts.current, BACKOFF_DELAYS.length - 1)];
      attempts.current += 1;
      setIsReconnecting(true);
      setNotice(t('arena_reconnecting'));
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(() => {
        if (!left.current && stateRef.current !== 'gameover') connect();
      }, delay);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, handleMessage, t]);

  // Connect to the room via JWT WebSocket.
  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setState('error');
      setNotice(t('arena_login_needed'));
      return;
    }
    left.current = false;
    connect();
    if (pingTimer.current) clearInterval(pingTimer.current);
    pingTimer.current = setInterval(() => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        missedPongs.current += 1;
        if (missedPongs.current >= 2) {
          try {
            ws.current.close();
          } catch {
            /* ignore */
          }
          return;
        }
        try {
          ws.current.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
        } catch {
          /* ignore */
        }
      }
    }, 15000);
    return () => {
      left.current = true;
      clearTimers();
      try {
        ws.current?.send(JSON.stringify({ type: 'leave_room' }));
      } catch {
        /* closing */
      }
      try {
        ws.current?.close();
      } catch {
        /* closing */
      }
      ws.current = null;
    };
  }, [code, user, authLoading, connect, t]);

  // Opponent disconnected grace period countdown
  useEffect(() => {
    if (!opponentDisconnected) return;
    const timer = setInterval(() => {
      setOpponentGraceSeconds((s) => {
        if (s <= 1) {
          clearInterval(timer);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [opponentDisconnected]);

  // Local countdown mirror (server is authoritative).
  useEffect(() => {
    if (state !== 'playing') return;
    if (timeLeft <= 0) return;
    const id = setInterval(() => {
      setTimeLeft((v) => {
        if (v <= 1) {
          setDisabled(true);
          return 0;
        }
        return v - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [state, timeLeft, qIndex]);

  const answer = (opt: string) => {
    if (picked || disabled || state !== 'playing') return;
    setPicked(opt);
    ws.current?.send(
      JSON.stringify({
        type: 'submit_answer',
        room_code: code,
        answer: opt,
        question_index: qIndex,
      }),
    );
  };

  const leave = () => {
    left.current = true;
    clearTimers();
    try {
      ws.current?.send(JSON.stringify({ type: 'leave_room' }));
    } catch {
      /* closing */
    }
    try {
      ws.current?.close();
    } catch {
      /* closing */
    }
    navigate('/arena');
  };

  const myScore = arenaScoreOf(rows, myId);
  const oppRows = arenaOpponentRows(rows, myId);
  const otherScore = oppRows.length > 0 ? (oppRows[0]?.score ?? 0) : 0;

  const nameOf = (p: DuelPlayer | null) => p?.name ?? '…';
  const myName =
    myId !== null && p1 && p2
      ? myId === p1.id
        ? nameOf(p1)
        : nameOf(p2)
      : t('arena_you');
  const oppName =
    myId !== null && p1 && p2
      ? myId === p1.id
        ? nameOf(p2)
        : nameOf(p1)
      : '…';

  return (
    <div style={{ maxWidth: 42 * 16, margin: '0 auto' }}>
      <h1>
        <SwordsIcon size={22} className="ico" /> {t('arena')} · {code}
      </h1>
      <p>
        <button className="btn sm" onClick={leave}>
          {t('arena_leave')}
        </button>
      </p>
      {opponentDisconnected && (
        <div className="duel-alert is-bad" role="status">
          <span aria-hidden="true">⚠️</span>
          <div>
            <strong>{t('arena_opp_reconnecting').replace('{s}', String(opponentGraceSeconds))}</strong>
            <p>{t('arena_opp_forfeit_hint')}</p>
          </div>
        </div>
      )}
      {isReconnecting && (
        <div className="duel-alert is-warn" role="status">
          <span aria-hidden="true">⚡</span>
          <strong>{t('arena_reconnecting')}</strong>
        </div>
      )}
      {notice && <p className="muted">{notice}</p>}

      {(state === 'session' || state === 'connecting') && (
        <div className="duel-skeleton" aria-busy="true" aria-label={t('loading')}>
          <div className="dsh-skeleton" style={{ height: 76 }} />
          <div className="dsh-skeleton-line" style={{ height: 22, width: '70%' }} />
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="dsh-skeleton" style={{ height: 52 }} />
          ))}
        </div>
      )}
      {state === 'error' && <p className="error">{notice || t('arena_ws_error')}</p>}

      {state === 'waiting' && (
        <div className="card" style={{ textAlign: 'center', padding: '2.5rem 1.5rem', maxWidth: 520, margin: '1.5rem auto' }}>
          <div style={{ marginBottom: 16 }}>
            <SwordsIcon size={56} />
          </div>
          <h2 style={{ marginBottom: 8 }}>{t('arena_waiting')}</h2>
          <p className="muted" style={{ marginBottom: 20 }}>{t('arena_wait_hint')}</p>

          <div
            style={{
              padding: '16px 20px',
              borderRadius: 12,
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px dashed rgba(255, 255, 255, 0.15)',
              marginBottom: 20,
            }}
          >
            <span style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'block', marginBottom: 4 }}>
              Xona kodi:
            </span>
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: '1.75rem',
                fontWeight: 800,
                letterSpacing: '0.25em',
                color: 'var(--primary, #38bdf8)',
              }}
            >
              {code}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button
              className="btn primary"
              onClick={copyInviteLink}
              style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px 20px' }}
            >
              {copied ? <Check size={18} /> : <LinkIcon size={18} />}
              {copied ? "Havola nusxalandi! ✅" : "🔗 Do'stni chorlash (Havoladan nusxa olish)"}
            </button>

            <a
              href={`https://t.me/share/url?url=${encodeURIComponent(`${window.location.origin}/arena/${code}`)}&text=${encodeURIComponent(`Men bilan 1v1 bilim jangida bellash! Xona kodi: ${code}`)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                background: '#0284c7',
                color: '#fff',
                borderColor: '#0284c7',
              }}
            >
              <Send size={16} />
              ✈️ Telegram orqali taklif qilish
            </a>
          </div>

          <p className="muted small" style={{ marginTop: 20 }}>
            ⚡ 8 soniya ichida boshqa o'yinchi topilmasa, teng kuchli intellektual sparring bot ulanadi!
          </p>
        </div>
      )}

      {state === 'countdown' && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem 1rem' }}>
          <div className={`duel-count${countdown <= 1 ? ' is-go' : ''}`} aria-live="assertive">
            {countdown <= 0 ? '⚔️' : Math.max(countdown, 1)}
          </div>
          <p className="duel-count__label">
            {countdown <= 0 ? t('arena_fight') : t('arena_starting')}
          </p>
          {p1 && p2 && (
            <p className="duel-versus">
              <strong className="is-me">{p1.name}</strong>
              <span aria-hidden="true">⚔️</span>
              <strong className="is-opp">{p2.name}</strong>
            </p>
          )}
        </div>
      )}

      {state === 'playing' && question && (
        <>
          {/* Top 2 Player Cards & Big Scoreboard */}
          <div className="bento-card" style={{ padding: '20px', borderRadius: 20, marginBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 16 }}>
              {/* Player 1 Card (You) */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #3B82F6, #1D4ED8)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#FFFFFF',
                    fontWeight: 900,
                    fontSize: 16,
                    boxShadow: '0 0 16px rgba(59, 130, 246, 0.4)',
                    border: '2px solid rgba(255, 255, 255, 0.2)',
                    flexShrink: 0,
                  }}
                >
                  {myName.slice(0, 2).toUpperCase()}
                </div>
                <div style={{ minWidth: 0 }}>
                  <b style={{ display: 'block', fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{myName}</b>
                  <span style={{ fontSize: 11, color: '#38BDF8', fontWeight: 700 }}>Siz (O'yinchi 1)</span>
                </div>
              </div>

              {/* Center: Katta hisob tablosu (4 : 3) */}
              <div style={{ textAlign: 'center', padding: '6px 20px', borderRadius: 16, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', minWidth: 120 }}>
                <span className="timer-mono" style={{ fontSize: 32, fontWeight: 900, letterSpacing: '0.08em', color: '#FBBF24' }}>
                  {myScore} : {otherScore}
                </span>
                <span style={{ display: 'block', fontSize: 11, fontWeight: 700, color: timeLeft <= 5 ? '#EF4444' : 'var(--text-secondary)' }}>
                  ⏱ {timeLeft}s qoldi
                </span>
              </div>

              {/* Player 2 Card (Opponent) */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 }}>
                <div style={{ textAlign: 'right', minWidth: 0 }}>
                  <b style={{ display: 'block', fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {oppName} {isBotDuel ? `(${t('arena_bot')})` : ''}
                  </b>
                  <span style={{ fontSize: 11, color: '#F43F5E', fontWeight: 700 }}>Raqib (O'yinchi 2)</span>
                </div>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #EF4444, #B91C1C)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#FFFFFF',
                    fontWeight: 900,
                    fontSize: 16,
                    boxShadow: '0 0 16px rgba(239, 68, 68, 0.4)',
                    border: '2px solid rgba(255, 255, 255, 0.2)',
                    flexShrink: 0,
                  }}
                >
                  {oppName.slice(0, 2).toUpperCase()}
                </div>
              </div>
            </div>

            {/* Pastga kamayib boruvchi taymer chizig'i */}
            <div style={{ height: 6, width: '100%', background: 'rgba(255, 255, 255, 0.08)', borderRadius: 999, overflow: 'hidden', marginTop: 16 }}>
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(100, Math.max(0, (timeLeft / 15) * 100))}%`,
                  background: timeLeft <= 4 ? '#EF4444' : 'linear-gradient(90deg, #10B981, #F59E0B)',
                  transition: 'width 1s linear',
                }}
              />
            </div>

            {streak >= 2 && (
              <p className="duel-streak" style={{ marginTop: 8 }}>
                <FlameIcon size={14} className="ico" /> x{streak} seriya!
              </p>
            )}
            {gained !== null && reveal !== null && (
              <p className="muted small" style={{ marginTop: 4 }}>
                +{gained} {t('points')}
              </p>
            )}
            {!opponentAnswered && <p className="muted small" style={{ marginTop: 4 }}>{t('arena_thinking')}</p>}
          </div>

          {/* Question Card & 4 Fast A, B, C, D Options */}
          <div className="bento-card" style={{ padding: '24px', borderRadius: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 800, color: 'var(--brand-gold)' }}>
                {t('arena_question_n').replace('{i}', String(total > 0 ? qIndex + 1 : qIndex)).replace('{n}', String(total))}
              </span>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>
                +{question.points} ball
              </span>
            </div>

            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, lineHeight: 1.5, margin: '0 0 20px', color: 'var(--text-primary)' }}>
              {question.question_text}
            </h2>

            {/* 4 Swift Variant Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: 12 }}>
              {OPTS.map((opt) => {
                const label = question[`option_${opt}` as keyof Question] as string;
                const isPicked = picked === opt;
                const isRight = reveal !== null && opt === reveal;
                const isWrong = reveal !== null && isPicked && opt !== reveal;

                return (
                  <button
                    key={opt}
                    type="button"
                    disabled={picked !== null || disabled}
                    onClick={() => answer(opt)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '14px 16px',
                      borderRadius: 14,
                      fontSize: 15,
                      fontWeight: 700,
                      cursor: picked !== null || disabled ? 'default' : 'pointer',
                      border: isRight
                        ? '2px solid #10B981'
                        : isWrong
                        ? '2px solid #EF4444'
                        : isPicked
                        ? '2px solid #F59E0B'
                        : '1.5px solid var(--border-subtle)',
                      background: isRight
                        ? 'rgba(16, 185, 129, 0.15)'
                        : isWrong
                        ? 'rgba(239, 68, 68, 0.15)'
                        : isPicked
                        ? 'rgba(245, 158, 11, 0.15)'
                        : 'var(--bg-elevated)',
                      color: isRight
                        ? '#10B981'
                        : isWrong
                        ? '#EF4444'
                        : isPicked
                        ? '#F59E0B'
                        : 'var(--text-primary)',
                      textAlign: 'left',
                      transition: 'all 0.15s ease',
                      boxShadow: isRight
                        ? '0 0 16px rgba(16, 185, 129, 0.3)'
                        : isPicked
                        ? '0 0 16px rgba(245, 158, 11, 0.3)'
                        : 'none',
                    }}
                  >
                    <span
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 8,
                        background: isRight
                          ? '#10B981'
                          : isWrong
                          ? '#EF4444'
                          : isPicked
                          ? '#F59E0B'
                          : 'var(--border-subtle)',
                        color: isRight || isWrong || isPicked ? '#FFFFFF' : 'var(--text-secondary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 900,
                        fontSize: 14,
                        fontFamily: 'JetBrains Mono, monospace',
                        flexShrink: 0,
                      }}
                    >
                      {opt.toUpperCase()}
                    </span>
                    <span style={{ flex: 1 }}>{label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {state === 'gameover' && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem 1rem' }}>
          <TrophyIcon size={56} />
          <h2>
            {result === 'win' && t('arena_win')}
            {result === 'lose' && t('arena_lose')}
            {result === 'draw' && t('arena_draw')}
            {!result && t('arena_game_over')}
          </h2>
          <p className="stat-value">
            {myScore} : {otherScore}
          </p>
          <div className="duel-rewards">
            <span className="duel-reward">⚡ +{rewards.xp} {t('xp')}</span>
            <span className="duel-reward">🪙 +{rewards.coins} {t('coins')}</span>
            <span className={`duel-reward is-elo ${rewards.elo >= 0 ? 'is-up' : 'is-down'}`}>
              ELO {rewards.elo >= 0 ? `▲ +${rewards.elo}` : `▼ ${rewards.elo}`}
            </span>
          </div>
          {result && (
            <p className={`duel-outcome is-${result}`}>
              {t(result === 'win' ? 'arena_win_msg' : result === 'lose' ? 'arena_lose_msg' : 'arena_draw_msg')}
            </p>
          )}
          <div className="duel-end-actions">
            <button className="ui-btn ui-btn--primary" onClick={() => navigate('/arena')}>
              {t('arena_play_again')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
