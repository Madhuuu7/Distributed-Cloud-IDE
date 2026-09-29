import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/auth/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import DashboardPage from './pages/DashboardPage';
import IDEPage from './pages/IDEPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import UsagePage from './pages/UsagePage';
import WorkspaceDetailPage from './pages/WorkspaceDetailPage';
import WorkspacesPage from './pages/WorkspacesPage';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/workspaces" element={<WorkspacesPage />} />
            <Route path="/workspaces/:workspaceId" element={<WorkspaceDetailPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/ide/:projectId" element={<IDEPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
