import React from 'react';
import { FilterState } from '../types';
import { uniqueCategories, uniqueLocations, uniqueAgeGroups } from '../data/activityData';
import { ChevronDown, ChevronUp, Search, Filter, X } from 'lucide-react';

interface FilterPanelProps {
  filters: FilterState;
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>;
}

interface FilterSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  count?: number;
}

const FilterSection: React.FC<FilterSectionProps> = ({ title, children, defaultOpen = false, count }) => {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);

  return (
    <div className="border-b border-neutral-200 py-4">
      <button
        className="flex w-full items-center justify-between text-left font-medium text-neutral-800"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center">
          {title}
          {count !== undefined && count > 0 && (
            <span className="ml-2 text-xs bg-primary-100 text-primary-800 px-2 py-0.5 rounded-full">
              {count}
            </span>
          )}
        </div>
        {isOpen ? <ChevronUp size={18} className="text-neutral-500" /> : <ChevronDown size={18} className="text-neutral-500" />}
      </button>
      {isOpen && <div className="mt-3">{children}</div>}
    </div>
  );
};

const FilterPanel: React.FC<FilterPanelProps> = ({ filters, setFilters }) => {
  const handleKeywordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters(prev => ({ ...prev, keyword: e.target.value }));
  };

  const handleCheckboxChange = (
    field: keyof Omit<FilterState, 'keyword'>,
    value: string
  ) => {
    setFilters(prev => {
      const currentValues = prev[field] as string[];
      if (currentValues.includes(value)) {
        return {
          ...prev,
          [field]: currentValues.filter(v => v !== value)
        };
      } else {
        return {
          ...prev,
          [field]: [...currentValues, value]
        };
      }
    });
  };

  const clearFilters = () => {
    setFilters({
      keyword: '',
      categories: [],
      locations: [],
      ageGroups: [],
      daysOfWeek: [],
      availability: [],
      language: []
    });
  };

  // Count active filters
  const getActiveFilterCount = (field: keyof Omit<FilterState, 'keyword'>) => {
    return (filters[field] as string[]).length;
  };

  // Get total active filters
  const getTotalActiveFilters = () => {
    return Object.keys(filters)
      .filter(key => key !== 'keyword')
      .reduce((total, key) => {
        const filterKey = key as keyof Omit<FilterState, 'keyword'>;
        return total + (filters[filterKey] as string[]).length;
      }, 0);
  };

  return (
    <div className="bg-white rounded-xl shadow-card p-5 h-full">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-neutral-800 font-heading">Filters</h2>
          {getTotalActiveFilters() > 0 && (
            <button 
              onClick={clearFilters}
              className="text-sm text-primary-600 hover:text-primary-800 flex items-center"
            >
              <X size={14} className="mr-1" />
              Clear all
            </button>
          )}
        </div>
        <div className="relative">
          <input
            type="text"
            placeholder="Search by keyword or code"
            className="w-full border border-neutral-300 rounded-lg py-2.5 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-primary-500 text-neutral-800 bg-neutral-50"
            value={filters.keyword}
            onChange={handleKeywordChange}
          />
          <Search className="absolute left-3 top-2.5 text-neutral-400" size={18} />
        </div>
      </div>

      <div className="space-y-1 mb-6">
        {getTotalActiveFilters() > 0 && (
          <div className="flex items-center mb-3">
            <Filter size={16} className="text-primary-600 mr-2" />
            <span className="text-sm font-medium text-neutral-700">Active filters: {getTotalActiveFilters()}</span>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {Object.entries(filters).map(([field, values]) => {
            if (field === 'keyword' || (values as string[]).length === 0) return null;
            
            return (values as string[]).map(value => (
              <div 
                key={`${field}-${value}`}
                className="bg-primary-50 text-primary-700 text-xs rounded-full px-3 py-1 flex items-center"
              >
                <span>{value}</span>
                <button 
                  onClick={() => handleCheckboxChange(field as keyof Omit<FilterState, 'keyword'>, value)}
                  className="ml-1.5 text-primary-500 hover:text-primary-700"
                >
                  <X size={14} />
                </button>
              </div>
            ));
          })}
        </div>
      </div>

      <FilterSection title="Category" defaultOpen={true} count={getActiveFilterCount('categories')}>
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          {uniqueCategories.map(category => (
            <div key={category} className="flex items-center">
              <input
                type="checkbox"
                id={`category-${category}`}
                checked={filters.categories.includes(category)}
                onChange={() => handleCheckboxChange('categories', category)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`category-${category}`} className="ml-2 text-sm text-neutral-700">
                {category}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Location" count={getActiveFilterCount('locations')}>
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          {uniqueLocations.map(location => (
            <div key={location} className="flex items-center">
              <input
                type="checkbox"
                id={`location-${location}`}
                checked={filters.locations.includes(location)}
                onChange={() => handleCheckboxChange('locations', location)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`location-${location}`} className="ml-2 text-sm text-neutral-700">
                {location}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Age Group" count={getActiveFilterCount('ageGroups')}>
        <div className="space-y-2">
          {uniqueAgeGroups.map(ageGroup => (
            <div key={ageGroup} className="flex items-center">
              <input
                type="checkbox"
                id={`age-${ageGroup}`}
                checked={filters.ageGroups.includes(ageGroup)}
                onChange={() => handleCheckboxChange('ageGroups', ageGroup)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`age-${ageGroup}`} className="ml-2 text-sm text-neutral-700">
                {ageGroup}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Day of Week" count={getActiveFilterCount('daysOfWeek')}>
        <div className="space-y-2">
          {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
            <div key={day} className="flex items-center">
              <input
                type="checkbox"
                id={`day-${day}`}
                checked={filters.daysOfWeek.includes(day as any)}
                onChange={() => handleCheckboxChange('daysOfWeek', day as any)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`day-${day}`} className="ml-2 text-sm text-neutral-700">
                {day}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Availability" count={getActiveFilterCount('availability')}>
        <div className="space-y-2">
          {['Open', 'Waitlist', 'Full'].map(status => (
            <div key={status} className="flex items-center">
              <input
                type="checkbox"
                id={`status-${status}`}
                checked={filters.availability.includes(status as any)}
                onChange={() => handleCheckboxChange('availability', status as any)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`status-${status}`} className="ml-2 text-sm text-neutral-700">
                {status}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Language" count={getActiveFilterCount('language')}>
        <div className="space-y-2">
          {['English', 'French'].map(lang => (
            <div key={lang} className="flex items-center">
              <input
                type="checkbox"
                id={`lang-${lang}`}
                checked={filters.language.includes(lang as any)}
                onChange={() => handleCheckboxChange('language', lang as any)}
                className="h-4 w-4 text-primary-600 rounded border-neutral-300 focus:ring-primary-500"
              />
              <label htmlFor={`lang-${lang}`} className="ml-2 text-sm text-neutral-700">
                {lang}
              </label>
            </div>
          ))}
        </div>
      </FilterSection>
    </div>
  );
};

export default FilterPanel;