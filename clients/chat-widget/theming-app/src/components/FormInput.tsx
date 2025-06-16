import React, { useState, useEffect } from 'react';

interface FormInputProps {
  label?: string;
  value: string | number;
  onChange: (value: string) => void;
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
  const [inputValue, setInputValue] = useState(String(value));

  useEffect(() => {
    setInputValue(String(value));
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    
    if (type === 'number') {
      if (newValue === '') {
        onChange('');
      } else {
        const numValue = Number(newValue);
        if (!isNaN(numValue)) {
          if (min !== undefined && numValue < min) {
            setInputValue(String(min));
            onChange(String(min));
          } else if (max !== undefined && numValue > max) {
            setInputValue(String(max));
            onChange(String(max));
          } else {
            onChange(newValue);
          }
        }
      }
    } else if (!maxLength || newValue.length <= maxLength) {
      onChange(newValue);
    }
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
          value={inputValue}
          onChange={handleChange}
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
              {inputValue.length}/{maxLength}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};