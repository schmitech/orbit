import { AlertTriangle } from 'lucide-react';

export function OutOfServicePage({ message }: { message: string }) {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4 py-12">
      <div className="max-w-lg w-full text-center space-y-6">
        <div className="flex justify-center">
          <div className="bg-white/10 rounded-full p-4">
            <AlertTriangle className="h-10 w-10 text-amber-300" aria-hidden="true" />
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-2xl font-semibold tracking-tight">Temporarily Unavailable</p>
        </div>
        <p className="text-sm text-white/60">
          {message}
        </p>
      </div>
    </div>
  );
}
