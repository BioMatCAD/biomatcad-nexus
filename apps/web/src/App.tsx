import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import { SystemStatusProvider } from "./context/SystemStatusContext";
import { ThemeProvider } from "./theme/ThemeProvider";
import { AboutPage } from "./pages/AboutPage";
import { DashboardPage } from "./pages/DashboardPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { MaterialDetailPage } from "./pages/MaterialDetailPage";
import { MaterialsPage } from "./pages/MaterialsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ObservabilityPage } from "./pages/ObservabilityPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RecipeDetailPage } from "./pages/RecipeDetailPage";
import { RecipeEditorPage } from "./pages/RecipeEditorPage";
import { ScientificDataPage } from "./pages/ScientificDataPage";
import { ScientificEntityDetailPage } from "./pages/ScientificEntityDetailPage";

export function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <SystemStatusProvider>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/materials"
              element={
                <ProtectedRoute>
                  <MaterialsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/materials/:materialId"
              element={
                <ProtectedRoute>
                  <MaterialDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/projects"
              element={
                <ProtectedRoute>
                  <ProjectsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/projects/:projectId"
              element={
                <ProtectedRoute>
                  <ProjectDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/projects/:projectId/recipes/new"
              element={
                <ProtectedRoute>
                  <RecipeEditorPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/recipes/:recipeId"
              element={
                <ProtectedRoute>
                  <RecipeDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/jobs/:jobId"
              element={
                <ProtectedRoute>
                  <JobDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/observability"
              element={
                <ProtectedRoute>
                  <ObservabilityPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/scientific-data"
              element={
                <ProtectedRoute>
                  <ScientificDataPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/scientific-data/:entityId"
              element={
                <ProtectedRoute>
                  <ScientificEntityDetailPage />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </SystemStatusProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
