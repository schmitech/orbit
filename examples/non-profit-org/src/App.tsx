import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import About from './pages/About';
import Contact from './pages/Contact';
import Events from './pages/Events';
import YouthPrograms from './pages/programs/YouthPrograms.tsx';
import SeniorServices from './pages/programs/SeniorServices.tsx';
import AdultEducation from './pages/programs/AdultEducation.tsx';
import FamilyServices from './pages/programs/FamilyServices.tsx';
import FinancialLiteracy from './pages/programs/FinancialLiteracy.tsx';
import ChatWidget from './ChatWidget.tsx';
import CommunityOutreach from './pages/programs/CommunityOutreach.tsx';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/events" element={<Events />} />
        <Route path="/programs/youth" element={<YouthPrograms />} />
        <Route path="/programs/seniors" element={<SeniorServices />} />
        <Route path="/programs/adult-education" element={<AdultEducation />} />
        <Route path="/programs/family" element={<FamilyServices />} />
        <Route path="/programs/financial" element={<FinancialLiteracy />} />
        <Route path="/programs/outreach" element={<CommunityOutreach />} />
      </Routes>
      <ChatWidget />
    </Layout>
  );
}

export default App;