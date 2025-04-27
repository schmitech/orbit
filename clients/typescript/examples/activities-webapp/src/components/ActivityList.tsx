import React from 'react';
import { Activity } from '../types';
import ActivityCard from './ActivityCard';
import { Grid, List, ChevronLeft, ChevronRight, SlidersHorizontal } from 'lucide-react';
import clsx from 'clsx';

interface ActivityListProps {
  activities: Activity[];
  loading?: boolean;
}

const ActivityList: React.FC<ActivityListProps> = ({ activities, loading = false }) => {
  const [viewMode, setViewMode] = React.useState<'list' | 'grid'>('list');
  const [currentPage, setCurrentPage] = React.useState(1);
  const [sortField, setSortField] = React.useState<keyof Activity>('startDate');
  const [sortDirection, setSortDirection] = React.useState<'asc' | 'desc'>('asc');
  
  const itemsPerPage = 10;
  const totalPages = Math.ceil(activities.length / itemsPerPage);
  
  const handleSort = (field: keyof Activity) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };
  
  const sortedActivities = React.useMemo(() => {
    return [...activities].sort((a, b) => {
      let aValue: any = a[sortField];
      let bValue: any = b[sortField];
      
      // Handle special cases for sorting
      if (sortField === 'startDate' || sortField === 'endDate') {
        aValue = new Date(aValue).getTime();
        bValue = new Date(bValue).getTime();
      }
      
      if (aValue < bValue) return sortDirection === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [activities, sortField, sortDirection]);
  
  const paginatedActivities = sortedActivities.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );
  
  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  
  const renderPagination = () => {
    if (totalPages <= 1) return null;
    
    const pageNumbers = [];
    const maxVisiblePages = 5;
    
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
    
    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(i);
    }
    
    return (
      <div className="flex items-center justify-center mt-8 space-x-1">
        <button
          onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="p-2 rounded-lg border border-neutral-300 disabled:opacity-50 hover:bg-neutral-100 transition-colors"
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        
        {startPage > 1 && (
          <>
            <button
              onClick={() => handlePageChange(1)}
              className="px-3 py-1 rounded-lg border border-neutral-300 hover:bg-neutral-100 transition-colors"
            >
              1
            </button>
            {startPage > 2 && <span className="px-1">...</span>}
          </>
        )}
        
        {pageNumbers.map(page => (
          <button
            key={page}
            onClick={() => handlePageChange(page)}
            className={clsx(
              'px-3 py-1 rounded-lg font-medium transition-colors',
              currentPage === page
                ? 'bg-primary-600 text-white border border-primary-600'
                : 'border border-neutral-300 hover:bg-neutral-100'
            )}
          >
            {page}
          </button>
        ))}
        
        {endPage < totalPages && (
          <>
            {endPage < totalPages - 1 && <span className="px-1">...</span>}
            <button
              onClick={() => handlePageChange(totalPages)}
              className="px-3 py-1 rounded-lg border border-neutral-300 hover:bg-neutral-100 transition-colors"
            >
              {totalPages}
            </button>
          </>
        )}
        
        <button
          onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="p-2 rounded-lg border border-neutral-300 disabled:opacity-50 hover:bg-neutral-100 transition-colors"
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    );
  };
  
  const renderSortButton = (field: keyof Activity, label: string) => {
    return (
      <button
        onClick={() => handleSort(field)}
        className={clsx(
          'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
          sortField === field 
            ? 'bg-primary-100 text-primary-800 border border-primary-200' 
            : 'text-neutral-600 hover:bg-neutral-100 border border-transparent'
        )}
      >
        {label}
        {sortField === field && (
          <span className="ml-1">
            {sortDirection === 'asc' ? '↑' : '↓'}
          </span>
        )}
      </button>
    );
  };
  
  if (loading) {
    return (
      <div className="flex justify-center items-center h-64 bg-white rounded-xl shadow-card">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500 mb-4"></div>
          <p className="text-neutral-500">Loading activities...</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="bg-white rounded-xl shadow-card p-5">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
        <h2 className="text-xl font-bold text-neutral-800 mb-2 sm:mb-0 font-heading flex items-center">
          Activities 
          <span className="ml-2 text-sm font-normal text-neutral-500 bg-neutral-100 px-2 py-0.5 rounded-full">
            {activities.length}
          </span>
        </h2>
        
        <div className="flex items-center space-x-2">
          <div className="flex border rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('list')}
              className={clsx(
                'p-2 transition-colors',
                viewMode === 'list' 
                  ? 'bg-primary-600 text-white' 
                  : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
              )}
              aria-label="List view"
            >
              <List size={18} />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={clsx(
                'p-2 transition-colors',
                viewMode === 'grid' 
                  ? 'bg-primary-600 text-white' 
                  : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
              )}
              aria-label="Grid view"
            >
              <Grid size={18} />
            </button>
          </div>
        </div>
      </div>
      
      <div className="mb-5 overflow-x-auto">
        <div className="flex items-center space-x-2 pb-2">
          <SlidersHorizontal size={16} className="text-neutral-400 mr-1" />
          <span className="text-sm font-medium text-neutral-500 mr-2">Sort by:</span>
          {renderSortButton('activityName', 'Name')}
          {renderSortButton('category', 'Category')}
          {renderSortButton('location', 'Location')}
          {renderSortButton('startDate', 'Start Date')}
          {renderSortButton('price', 'Price')}
          {renderSortButton('spotsAvailable', 'Availability')}
        </div>
      </div>
      
      {activities.length === 0 ? (
        <div className="text-center py-16 bg-neutral-50 rounded-lg border border-neutral-200">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 mx-auto text-neutral-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-neutral-500 text-lg font-medium">No activities found matching your criteria.</p>
          <p className="text-neutral-400 mt-2">Try adjusting your filters or search term.</p>
        </div>
      ) : viewMode === 'list' ? (
        <div className="space-y-5">
          {paginatedActivities.map(activity => (
            <ActivityCard key={activity.id} activity={activity} viewMode="list" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {paginatedActivities.map(activity => (
            <ActivityCard key={activity.id} activity={activity} viewMode="grid" />
          ))}
        </div>
      )}
      
      {renderPagination()}
    </div>
  );
};

export default ActivityList;