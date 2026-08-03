import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export function FeedbackThanks() {
  const { t } = useTranslation();
  return (
    <span className="ml-1 inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-emerald-500 px-2 py-0.5 text-[11px] font-medium text-white shadow-sm animate-fadeIn dark:bg-emerald-600">
      <Check className="h-3 w-3" />
      {t('message.feedback.thanks')}
    </span>
  );
}
