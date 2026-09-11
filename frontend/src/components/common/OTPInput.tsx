import React, { useRef, useEffect, useState } from 'react';

interface OTPInputProps {
  length?: number;
  value: string;
  onChange: (otp: string) => void;
  onComplete?: (otp: string) => void;
  disabled?: boolean;
  onResend?: () => void;
  expiresInSeconds?: number;
}

export const OTPInput: React.FC<OTPInputProps> = ({
  length = 6,
  value,
  onChange,
  onComplete,
  disabled = false,
  onResend,
  expiresInSeconds = 300,
}) => {
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);
  const [timeLeft, setTimeLeft] = useState(expiresInSeconds);

  useEffect(() => {
    setTimeLeft(expiresInSeconds);
  }, [expiresInSeconds]);

  useEffect(() => {
    if (timeLeft <= 0) return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [timeLeft]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>, index: number) => {
    const inputVal = e.target.value.replace(/\D/g, '');
    if (!inputVal) {
      const digits = value.split('');
      digits[index] = '';
      const newOtp = digits.join('');
      onChange(newOtp);
      return;
    }

    const digit = inputVal[inputVal.length - 1];
    const digits = value.split('');
    while (digits.length <= index) {
      digits.push('');
    }
    digits[index] = digit;
    const newOtp = digits.slice(0, length).join('');
    onChange(newOtp);

    if (index < length - 1) {
      inputsRef.current[index + 1]?.focus();
    }

    if (newOtp.length === length && onComplete) {
      onComplete(newOtp);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === 'Backspace') {
      if (!value[index] && index > 0) {
        inputsRef.current[index - 1]?.focus();
      }
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (pasted) {
      onChange(pasted);
      if (pasted.length === length && onComplete) {
        onComplete(pasted);
      }
      const focusIndex = Math.min(pasted.length, length - 1);
      inputsRef.current[focusIndex]?.focus();
    }
  };

  return (
    <div className="flex flex-col items-center">
      <div className="flex items-center justify-center gap-2 sm:gap-3 mb-3">
        {Array.from({ length }).map((_, idx) => (
          <input
            key={idx}
            ref={(el) => {
              inputsRef.current[idx] = el;
            }}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={value[idx] || ''}
            onChange={(e) => handleChange(e, idx)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            onPaste={handlePaste}
            disabled={disabled}
            className={`w-11 h-12 sm:w-12 sm:h-14 text-center font-mono text-xl font-extrabold text-slate-900 rounded-xl border transition-all ${
              value[idx]
                ? 'border-red-500 bg-red-50/40 shadow-2xs'
                : 'border-slate-200 bg-slate-50 focus:border-slate-400 focus:bg-white'
            } outline-none disabled:opacity-50`}
          />
        ))}
      </div>

      {/* Timer & Resend Controls */}
      <div className="flex items-center justify-between w-full max-w-xs text-xs font-sans text-slate-500 pt-1">
        <div>
          {timeLeft > 0 ? (
            <span className="text-slate-600 font-medium">
              Expires in <strong className="text-slate-800 font-mono">{formatTime(timeLeft)}</strong>
            </span>
          ) : (
            <span className="text-red-600 font-semibold">Code expired</span>
          )}
        </div>

        {onResend && (
          <button
            type="button"
            onClick={() => {
              setTimeLeft(expiresInSeconds);
              onResend();
            }}
            disabled={disabled || timeLeft > 240}
            className="text-slate-700 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed underline font-semibold"
          >
            Resend Code
          </button>
        )}
      </div>
    </div>
  );
};
