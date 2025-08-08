import React from 'react';

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
  required = false,
  disabled = false
}) => {

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;

    // For numeric inputs, respect provided bounds while allowing empty typing
    if (type === 'number') {
      // Allow clearing the field for editing
      if (raw === '') {
        onChange(raw);
        return;
      }

      const n = Number(raw);
      // If not a valid number, just pass through
      if (Number.isNaN(n)) {
        onChange(raw);
        return;
      }

      // Enforce max immediately to keep field bounded while typing
      if (typeof max === 'number' && n > max) {
        onChange(String(max));
        return;
      }

      // Do not clamp to min on change to avoid blocking partial input (handled onBlur)
      onChange(raw);
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
          type={type}
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
            showCharacterCount && maxLength && type !== 'number' ? 'pr-16' : ''
          } ${inputClassName}`}
        />
        {showCharacterCount && maxLength && type !== 'number' && (
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
