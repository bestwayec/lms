import { useAuth } from '../context/AuthContext';
import Onboarding from '../pages/Onboarding';

interface OnboardingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export default function OnboardingModal({ isOpen, onClose, onSuccess }: OnboardingModalProps) {
  const { user } = useAuth();

  const role = (user?.role || '').toLowerCase();
  const isStaffOrTeacher =
    role === 'admin' || role === 'teacher' || role === 'superadmin' || role === 'center_admin' || Boolean(user?.is_superuser);
  const isStudent = role === 'student' && !isStaffOrTeacher;

  if (!isOpen || !isStudent || user?.onboarding_completed) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Smart Onboarding So'rovnoma"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'var(--bg-page, var(--bg))',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Onboarding
        isModal
        onClose={onClose}
        onSuccess={onSuccess}
      />
    </div>
  );
}
