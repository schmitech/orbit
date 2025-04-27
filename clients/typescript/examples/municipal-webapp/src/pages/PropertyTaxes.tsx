import React from 'react';
import { DollarSign, Calendar, FileText, Calculator, HelpCircle, AlertTriangle, Search } from 'lucide-react';

const PropertyTaxes: React.FC = () => {
  const importantDates = [
    {
      date: 'January 31, 2024',
      description: 'First installment due'
    },
    {
      date: 'July 31, 2024',
      description: 'Second installment due'
    },
    {
      date: 'December 1, 2024',
      description: 'New assessment notices mailed'
    }
  ];

  const taxRates = [
    {
      category: 'Residential',
      rate: '1.25%',
      description: 'Single-family homes and condominiums'
    },
    {
      category: 'Commercial',
      rate: '2.50%',
      description: 'Business and retail properties'
    },
    {
      category: 'Industrial',
      rate: '2.75%',
      description: 'Manufacturing and warehouse facilities'
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-6xl mx-auto">
          {/* Hero Section */}
          <div className="bg-gradient-to-r from-green-900 to-green-700 text-white rounded-lg p-8 mb-12">
            <h1 className="text-4xl font-bold mb-4">Property Taxes</h1>
            <p className="text-xl opacity-90">
              Information about property taxes, payments, and assessments
            </p>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <a href="/taxes/pay" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <DollarSign className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Pay Taxes</h3>
              <p className="text-gray-600">Make a payment online</p>
            </a>
            <a href="/taxes/calculator" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Calculator className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Tax Calculator</h3>
              <p className="text-gray-600">Estimate your property taxes</p>
            </a>
            <a href="/taxes/lookup" className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition">
              <Search className="w-6 h-6 text-green-600 mb-3" />
              <h3 className="font-semibold mb-2">Property Lookup</h3>
              <p className="text-gray-600">Search property records</p>
            </a>
          </div>

          {/* Important Dates */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <Calendar className="w-6 h-6 text-green-600" />
              <h2 className="text-2xl font-bold">Important Dates</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {importantDates.map(item => (
                <div key={item.date} className="bg-gray-50 rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-2">{item.date}</h3>
                  <p className="text-gray-600">{item.description}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Tax Rates */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <FileText className="w-6 h-6 text-green-600" />
              <h2 className="text-2xl font-bold">Tax Rates</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {taxRates.map(rate => (
                <div key={rate.category} className="border rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-2">{rate.category}</h3>
                  <p className="text-2xl font-bold text-green-600 mb-2">{rate.rate}</p>
                  <p className="text-gray-600">{rate.description}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Payment Options */}
          <section className="bg-white rounded-lg shadow-md p-6 mb-12">
            <h2 className="text-2xl font-bold mb-6">Payment Options</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold text-lg mb-2">Online Payment</h3>
                <ul className="space-y-2 text-gray-600">
                  <li>Credit/Debit Card (2.5% fee)</li>
                  <li>E-Check (No fee)</li>
                  <li>Available 24/7</li>
                  <li>Instant confirmation</li>
                </ul>
              </div>
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold text-lg mb-2">Other Methods</h3>
                <ul className="space-y-2 text-gray-600">
                  <li>Mail: Check or Money Order</li>
                  <li>In-Person: Cash, Check, or Card</li>
                  <li>Phone: Credit Card (2.5% fee)</li>
                  <li>Auto-Pay: Monthly installments</li>
                </ul>
              </div>
            </div>
          </section>

          {/* FAQ Section */}
          <section className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center space-x-3 mb-6">
              <HelpCircle className="w-6 h-6 text-green-600" />
              <h2 className="text-2xl font-bold">Frequently Asked Questions</h2>
            </div>
            <div className="space-y-6">
              <div>
                <h3 className="font-semibold mb-2">How are property taxes calculated?</h3>
                <p className="text-gray-600">Property taxes are calculated based on the assessed value of your property multiplied by the applicable tax rate for your property type and location.</p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">What payment methods are accepted?</h3>
                <p className="text-gray-600">We accept payments online via credit card, debit card, or e-check. You can also pay by mail or in person at City Hall.</p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">How can I appeal my assessment?</h3>
                <p className="text-gray-600">Property owners can appeal their assessment within 30 days of receiving their assessment notice. Appeals can be filed online or in person at the Assessor's Office.</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default PropertyTaxes;