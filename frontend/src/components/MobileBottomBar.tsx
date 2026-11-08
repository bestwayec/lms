import BottomNav from './BottomNav';

interface MobileBottomBarProps {
  onOpenProfile?: () => void;
}

/** Backward-compatible export mapping to BottomNav. */
export default function MobileBottomBar({ onOpenProfile }: MobileBottomBarProps) {
  return <BottomNav onOpenProfile={onOpenProfile} />;
}
