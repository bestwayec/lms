import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Home, FileText, Users, Trophy, User } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LangContext';
import { hapticSelect } from '../lib/haptics';

interface BottomNavProps {
  onOpenProfile?: () => void;
}

/**
 * Mobile-First Sticky Bottom Navigation Bar (App Shell)
 * Features:
 * - 5 core destinations: Bosh sahifa, Testlar, Guruhim, Reyting, Profil
 * - Safe area support (pb-[max(1rem,env(safe-area-inset-bottom))])
 * - Frosted glass backdrop (glassmorphism blur)
 * - Vibrant gradient active state with glowing indicator dot
 * - Auto-hide when mobile virtual keyboard is open
 */
export default function BottomNav({ onOpenProfile }: BottomNavProps) {
  const { user, openAuthModal } = useAuth();
  const { t } = useLang();
  const { pathname } = useLocation();
  const [isKeyboardOpen, setIsKeyboardOpen] = useState(false);

  useEffect(() => {
    const handleFocusIn = (e: FocusEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        setIsKeyboardOpen(true);
      }
    };

    const handleFocusOut = () => {
      setIsKeyboardOpen(false);
    };

    const handleResize = () => {
      if (window.visualViewport) {
        const diff = window.innerHeight - window.visualViewport.height;
        setIsKeyboardOpen(diff > 120);
      }
    };

    window.addEventListener('focusin', handleFocusIn);
    window.addEventListener('focusout', handleFocusOut);
    window.visualViewport?.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('focusin', handleFocusIn);
      window.removeEventListener('focusout', handleFocusOut);
      window.visualViewport?.removeEventListener('resize', handleResize);
    };
  }, []);

  const handleProfileClick = (e: React.MouseEvent) => {
    if (onOpenProfile) {
      e.preventDefault();
      onOpenProfile();
      return;
    }
    if (!user) {
      e.preventDefault();
      openAuthModal('login');
    }
  };

  const navItems = [
    {
      to: user ? '/dashboard' : '/',
      label: t('bnav_home', 'Bosh sahifa'),
      Icon: Home,
      isActive: pathname === '/' || pathname === '/dashboard',
    },
    {
      to: '/tests',
      label: t('bnav_tests', 'Testlar'),
      Icon: FileText,
      isActive: pathname.startsWith('/tests') || pathname.startsWith('/take'),
    },
    {
      to: '/groups',
      label: t('bnav_groups', 'Guruhim'),
      Icon: Users,
      isActive: pathname.startsWith('/groups') || pathname.startsWith('/join'),
    },
    {
      to: '/leaderboard',
      label: t('bnav_leaderboard', 'Reyting'),
      Icon: Trophy,
      isActive: pathname.startsWith('/leaderboard') || pathname.startsWith('/arena'),
    },
    {
      to: '/profile',
      label: t('bnav_profile', 'Profil'),
      Icon: User,
      onClick: handleProfileClick,
      isActive: pathname.startsWith('/profile'),
    },
  ];

  return (
    <nav
      className="bnav bnav--glass"
      aria-label={t('bnav_label', 'Asosiy navigatsiya')}
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 60,
        backdropFilter: 'blur(20px) saturate(190%)',
        WebkitBackdropFilter: 'blur(20px) saturate(190%)',
        backgroundColor: 'var(--bnav-bg, rgba(15, 23, 42, 0.88))',
        borderTop: '1px solid var(--bnav-border, rgba(255, 255, 255, 0.08))',
        paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom, 12px))',
        paddingTop: '6px',
        paddingLeft: '6px',
        paddingRight: '6px',
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        boxShadow: '0 -4px 20px rgba(0, 0, 0, 0.25)',
        transform: isKeyboardOpen ? 'translateY(100%)' : 'translateY(0)',
        opacity: isKeyboardOpen ? 0 : 1,
        pointerEvents: isKeyboardOpen ? 'none' : 'auto',
        transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease',
      }}
    >
      {navItems.map(({ to, label, Icon, isActive, onClick }) => {
        return (
          <NavLink
            key={to}
            to={to}
            onClick={(e) => {
              hapticSelect();
              if (onClick) onClick(e);
            }}
            className={`bnav__item ${isActive ? 'is-on is-active' : ''}`}
            aria-current={isActive ? 'page' : undefined}
            style={{
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '3px',
              textDecoration: 'none',
              padding: '4px 2px',
              minWidth: 0,
              transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              WebkitTapHighlightColor: 'transparent',
            }}
          >
            <div
              style={{
                position: 'relative',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 36,
                height: 28,
                borderRadius: 10,
                background: isActive ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.18), rgba(217, 119, 6, 0.08))' : 'transparent',
                transition: 'all 0.2s ease',
              }}
            >
              <Icon
                size={21}
                strokeWidth={isActive ? 2.5 : 1.8}
                style={{
                  color: isActive ? '#f59e0b' : 'var(--muted, #94a3b8)',
                  filter: isActive ? 'drop-shadow(0 0 6px rgba(245, 158, 11, 0.55))' : 'none',
                  transition: 'all 0.2s ease',
                }}
                aria-hidden="true"
              />
            </div>
            <span
              style={{
                fontSize: '11px',
                fontWeight: isActive ? 700 : 500,
                color: isActive ? '#f59e0b' : 'var(--muted, #94a3b8)',
                letterSpacing: isActive ? '0.01em' : 'normal',
                maxWidth: '100%',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                lineHeight: 1.1,
                transition: 'color 0.2s ease',
              }}
            >
              {label}
            </span>
            {isActive && (
              <span
                className="bnav-glow-dot"
                style={{
                  position: 'absolute',
                  bottom: -1,
                  width: 4,
                  height: 4,
                  borderRadius: '50%',
                  backgroundColor: '#f59e0b',
                  boxShadow: '0 0 8px 1.5px #f59e0b, 0 0 14px 2px rgba(245, 158, 11, 0.7)',
                  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                }}
              />
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}
