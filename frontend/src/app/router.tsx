import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { LoginPage } from "@/auth/LoginPage";
import { Skeleton } from "@/components/ui";
import { Layout } from "./Layout";

const Landing = lazy(() => import("@/pages/Landing"));
const Overview = lazy(() => import("@/pages/Overview"));
const Runs = lazy(() => import("@/pages/Runs"));
const RunDetail = lazy(() => import("@/pages/RunDetail"));
const Approvals = lazy(() => import("@/pages/Approvals"));
const Agents = lazy(() => import("@/pages/Agents"));
const Workflows = lazy(() => import("@/pages/Workflows"));
const WorkflowBuilder = lazy(() => import("@/pages/WorkflowBuilder"));
const Connectors = lazy(() => import("@/pages/Connectors"));
const Simulators = lazy(() => import("@/pages/Simulators"));
const Settings = lazy(() => import("@/pages/Settings"));

/** Signed-out visitors see the landing page at "/" and are sent to sign in everywhere else. */
function Root() {
  const { user } = useAuth();
  const loc = useLocation();
  if (user) return <Layout />;
  if (loc.pathname === "/") {
    return (
      <Suspense fallback={<div className="min-h-dvh bg-paper" />}>
        <Landing />
      </Suspense>
    );
  }
  return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
}

const page = (el: ReactNode) => <Suspense fallback={<Skeleton className="h-64" />}>{el}</Suspense>;

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: <Root />,
    children: [
      { index: true, element: page(<Overview />) },
      { path: "runs", element: page(<Runs />) },
      { path: "runs/:runId", element: page(<RunDetail />) },
      { path: "approvals", element: page(<Approvals />) },
      { path: "agents", element: page(<Agents />) },
      { path: "workflows", element: page(<Workflows />) },
      { path: "workflows/new", element: page(<WorkflowBuilder />) },
      { path: "workflows/:workflowId", element: page(<WorkflowBuilder />) },
      { path: "connectors", element: page(<Connectors />) },
      { path: "simulators", element: page(<Simulators />) },
      { path: "settings", element: page(<Settings />) },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
