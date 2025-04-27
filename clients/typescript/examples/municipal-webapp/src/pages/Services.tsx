import React from 'react';
import { Building2, Droplet, Recycle, FileText, Briefcase, Book, Bus } from 'lucide-react';

const Services: React.FC = () => {
  const services = [
    {
      id: 'utilities',
      title: 'Utilities',
      icon: Droplet,
      description: 'Essential services for your home and business',
      sections: [
        {
          title: 'Water Services',
          content: `Our Water Services Division ensures that every resident has access to clean, safe drinking water 24/7. We maintain over 500 kilometers of water mains and conduct over 50,000 water quality tests annually to meet the highest safety standards.

Last year, we achieved a 99.9% compliance rate with federal water quality guidelines, demonstrating our commitment to excellence in water service delivery.`,
          stats: [
            { label: 'Daily Water Supply', value: '150 million liters' },
            { label: 'Quality Tests/Year', value: '50,000+' },
            { label: 'Service Reliability', value: '99.9%' }
          ]
        },
        {
          title: 'Waste Management',
          content: `Our comprehensive waste management program includes weekly garbage collection, bi-weekly recycling pickup, and seasonal yard waste collection. Through our innovative recycling initiatives, we've reduced landfill waste by 40% since 2020.

Download our Waste Wise app to get personalized collection schedules, disposal guidelines, and instant notifications about service changes.`,
          stats: [
            { label: 'Recycling Rate', value: '65%' },
            { label: 'Annual Waste Reduction', value: '40%' },
            { label: 'Households Served', value: '85,000+' }
          ]
        }
      ]
    },
    {
      id: 'permits',
      title: 'Building & Permits',
      icon: Building2,
      description: 'Everything you need for construction and renovation projects',
      sections: [
        {
          title: 'Building Permits',
          content: `Our streamlined permit process ensures your construction project meets all safety and zoning requirements. Most residential permits are processed within 10 business days, with our new online application system available 24/7.

Our expert staff reviewed over 2,500 permit applications last year, contributing to safe and sustainable development throughout our city.`,
          stats: [
            { label: 'Average Processing Time', value: '10 days' },
            { label: 'Online Applications', value: '75%' },
            { label: 'Customer Satisfaction', value: '4.5/5' }
          ]
        }
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold text-gray-900 mb-8">City Services</h1>
          
          <div className="space-y-12">
            {services.map(service => (
              <div key={service.id} className="bg-white rounded-lg shadow-md overflow-hidden">
                <div className="p-6 border-b border-gray-200">
                  <div className="flex items-center space-x-4">
                    <service.icon className="w-8 h-8 text-blue-600" />
                    <div>
                      <h2 className="text-2xl font-bold text-gray-900">{service.title}</h2>
                      <p className="text-gray-600">{service.description}</p>
                    </div>
                  </div>
                </div>

                <div className="p-6 space-y-8">
                  {service.sections.map((section, index) => (
                    <div key={index} className="space-y-4">
                      <h3 className="text-xl font-semibold text-gray-900">{section.title}</h3>
                      <p className="text-gray-700 whitespace-pre-wrap">{section.content}</p>
                      
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
                        {section.stats.map((stat, statIndex) => (
                          <div key={statIndex} className="bg-gray-50 p-4 rounded-lg">
                            <p className="text-sm text-gray-600">{stat.label}</p>
                            <p className="text-2xl font-bold text-blue-600">{stat.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-12 bg-blue-50 rounded-lg p-6">
            <h2 className="text-xl font-bold text-blue-900 mb-4">Need Assistance?</h2>
            <p className="text-blue-800 mb-4">
              Our customer service team is available Monday through Friday, 8:00 AM to 5:00 PM.
              For emergency services, please call our 24/7 hotline.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <button className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
                Contact Support
              </button>
              <button className="bg-white text-blue-600 px-6 py-2 rounded-lg hover:bg-gray-50 transition">
                View FAQs
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Services;