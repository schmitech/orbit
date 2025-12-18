import React, { useState } from 'react';

interface FormInputProps {
  label?: string;
  value: string | number;
  onChange: (value: string) => void;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  placeholder?: string;
  type?: 'text' | 'number' | 'email' | 'password';
  className?: string;
  inputClassName?: string;
  min?: number;
  max?: number;
  maxLength?: number;
  showCharacterCount?: boolean;
  showPasswordToggle?: boolean;
  required?: boolean;
  disabled?: boolean;
}

export const FormInput: React.FC<FormInputProps> = ({
  label,
  value,
  onChange,
  onBlur,
  placeholder,
  type = 'text',
  className = "",
  inputClassName = "",
  min,
  max,
  maxLength,
  showCharacterCount = false,
  showPasswordToggle = false,
  required = false,
  disabled = false
}) => {
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;

    if (type === 'number') {
      const numericValue = raw.replace(/[^0-9]/g, '');

      if (numericValue === '') {
        onChange('');
        return;
      }
      
      const n = Number(numericValue);

      if (typeof max === 'number' && n > max) {
        onChange(String(max));
        return;
      }
      
      onChange(numericValue);
      return;
    }

    onChange(raw);
  };

  return (
    <div className={className}>
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <div className="relative">
        <input
          type={type === 'number' ? 'text' : (type === 'password' && showPasswordToggle ? (showPassword ? 'text' : 'password') : type)}
          inputMode={type === 'number' ? 'numeric' : undefined}
          pattern={type === 'number' ? '[0-9]*' : undefined}
          value={value}
          onChange={handleChange}
          onBlur={onBlur}
          placeholder={placeholder}
          min={min}
          max={max}
          maxLength={maxLength}
          required={required}
          disabled={disabled}
          className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed ${
            (showCharacterCount && maxLength && type !== 'number') || showPasswordToggle ? 'pr-10' : ''
          } ${inputClassName}`}
        />
        {showPasswordToggle && type === 'password' && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none focus:text-gray-600"
            disabled={disabled}
          >
            {showPassword ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                <circle cx="12" cy="12" r="3" strokeWidth="2" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7l10 10" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            )}
          </button>
        )}
        {showCharacterCount && maxLength && type !== 'number' && !showPasswordToggle && (
          <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
            <span className="text-xs text-gray-400 bg-white px-1">
              {String(value).length}/{maxLength}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
