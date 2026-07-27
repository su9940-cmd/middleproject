import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import WorkerScreen from "./pages/WorkerScreen.jsx";
import ManagerScreen from "./pages/ManagerScreen.jsx";
import MaintenanceQueue from "./pages/MaintenanceQueue.jsx";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/machines/:machineId/worker" element={<WorkerScreen />} />
        <Route path="/machines/:machineId/manager" element={<ManagerScreen />} />
        <Route path="/maintenance" element={<MaintenanceQueue />} />
      </Routes>
    </Layout>
  );
}
