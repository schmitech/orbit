import React from 'react';

interface FormTextareaProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  textareaClassName?: string;
  maxLength?: number;
  showCharacterCount?: boolean;
  required?: boolean;
  disabled?: boolean;
}

export const FormTextarea: React.FC<FormTextareaProps> = ({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  className = "",
  textareaClassName = "",
  maxLength,
  showCharacterCount = false,
  required = false,
  disabled = false
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    if (!maxLength || newValue.length <= maxLength) {
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
        <textarea
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          rows={rows}
          maxLength={maxLength}
          required={required}
          disabled={disabled}
          className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed resize-none ${
            showCharacterCount && maxLength ? 'pr-16 pb-8' : ''
          } ${textareaClassName}`}
        />
        {showCharacterCount && maxLength && (
          <div className="absolute right-3 bottom-3 pointer-events-none">
            <span className="text-xs text-gray-400 bg-white px-1">
              {value.length}/{maxLength}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};