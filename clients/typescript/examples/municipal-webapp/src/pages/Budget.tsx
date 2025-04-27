import React from 'react';
import { DollarSign, PieChart, TrendingUp, FileText, Download, Search } from 'lucide-react';

const Budget: React.FC = () => {
  const budgetHighlights = [
    {
      category: 'Public Safety',
      amount: '$125M',
      percentage: '30%',
      change: '+5%'
    },
    {
      category: 'Infrastructure',
      amount: '$82M',
      percentage: '20%',
      change: '+8%'
    },
    {
      category: 'Parks & Recreation',
      amount: '$41M',
      percentage: '10%',
      change: '+3%'
    }
  ];

  const documents = [
    {
      title: 'FY 2024 Adopted Budget',
      type: 'PDF',
      size: '2.5 MB',
      date: '2024-01-15'
    },
    {
      title: 'Budget Presentation',
      type: 'PDF',
      size: '1.8 MB',
      date: '2024-01-15'
    },
    {
      title: 'Financial Reports Q4 2023',
      type: 'PDF',
      size: '1.2 MB',
      date: '2024-01-10'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-green-900 to-green-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">City Budget</h1>
            <p className="text-xl opacity-90">
              Transparent financial management for our community
            </p>
          </div>

          {/* Budget Overview */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <DollarSign className="w-6 h-6 text-green-600" />
              <h2 className="text-2xl font-bold">Budget Overview</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {budgetHighlights.map(item => (
                <div key={item.category} className="bg-gray-50 rounded-lg p-4">
                  <h3 className="font-semibold mb-2">{item.category}</h3>
                  <div className="flex justify-between items-baseline">
                    <span className="text-2xl font-bold text-green-600">{item.amount}</span>
                    <span className="text-sm text-gray-600">{item.percentage}</span>
                  </div>
                  <div className="mt-2 text-sm">
                    <span className={`font-semibold ${
                      item.change.startsWith('+') ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {item.change} from previous year
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Budget Documents */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <FileText className="w-6 h-6 text-green-600" />
              <h2 className="text-2xl font-bold">Budget Documents</h2>
            </div>
            <div className="space-y-4">
              {documents.map(doc => (
                <div key={doc.title} className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <h3 className="font-semibold">{doc.title}</h3>
                    <p className="text-sm text-gray-600">
                      {doc.type} • {doc.size} • Updated {new Date(doc.date).toLocaleDateString()}
                    </p>
                  </div>
                  <button className="flex items-center space-x-2 text-green-600 hover:text-green-700">
                    <Download className="w-5 h-5" />
                    <span>Download</span>
                  </button>
                </div>
              ))}
            </div>
          </section>

          {/* Quick Links */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/budget/explorer" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <PieChart className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Budget Explorer</h3>
              <p className="text-gray-600">Interactive visualization of city spending</p>
            </a>
            <a href="/budget/reports" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <TrendingUp className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Financial Reports</h3>
              <p className="text-gray-600">View detailed financial statements</p>
            </a>
            <a href="/budget/search" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Search className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Search Expenses</h3>
              <p className="text-gray-600">Look up specific budget items</p>
            </a>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Budget;