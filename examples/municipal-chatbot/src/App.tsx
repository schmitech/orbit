import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import Services from './pages/Services';
import Government from './pages/Government';
import Residents from './pages/Residents';
import Business from './pages/Business';
import Parks from './pages/Parks';
import Transportation from './pages/Transportation';
import Elections from './pages/Elections';
import Budget from './pages/Budget';
import BusinessDirectory from './pages/BusinessDirectory';
import Parking from './pages/Parking';
import PropertyTaxes from './pages/PropertyTaxes';
import Contact from './pages/Contact';
import Employment from './pages/Employment';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="/services" element={<Services />} />
          <Route path="/government" element={<Government />} />
          <Route path="/residents" element={<Residents />} />
          <Route path="/business" element={<Business />} />
          <Route path="/parks" element={<Parks />} />
          <Route path="/transportation" element={<Transportation />} />
          <Route path="/government/elections" element={<Elections />} />
          <Route path="/government/budget" element={<Budget />} />
          <Route path="/business/directory" element={<BusinessDirectory />} />
          <Route path="/services/parking" element={<Parking />} />
          <Route path="/services/property-taxes" element={<PropertyTaxes />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/jobs" element={<Employment />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;