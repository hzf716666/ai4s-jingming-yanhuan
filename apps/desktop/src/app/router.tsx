import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { SessionPage } from "./routes/SessionPage";
import { LiveSessionPage } from "./routes/LiveSessionPage";
import { SkillsPage } from "./routes/SkillsPage";
import { NotebooksPage } from "./routes/NotebooksPage";
import { FilesPage } from "./routes/FilesPage";
import { RunsPage } from "./routes/RunsPage";
import { ProjectsPage } from "./routes/ProjectsPage";
import { SettingsPage } from "./routes/SettingsPage";
import { DataMapPage } from "./routes/data/DataMapPage";
import { ExtractionListPage } from "./routes/data/ExtractionListPage";
import { ExtractionNewPage } from "./routes/data/ExtractionNewPage";
import { ExtractionProgressPage } from "./routes/data/ExtractionProgressPage";
import { ExtractionResultPage } from "./routes/data/ExtractionResultPage";
import { NotFound } from "./routes/NotFound";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/live" replace /> },
      { path: "live", element: <LiveSessionPage /> },
      { path: "live/:sessionId", element: <LiveSessionPage /> },
      { path: "example/:sessionId", element: <SessionPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "notebooks", element: <NotebooksPage /> },
      { path: "files", element: <FilesPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "settings/:section", element: <SettingsPage /> },
      { path: "data/map", element: <DataMapPage /> },
      { path: "data/extraction", element: <ExtractionListPage /> },
      { path: "data/extraction/new", element: <ExtractionNewPage /> },
      { path: "data/extraction/:taskId/progress", element: <ExtractionProgressPage /> },
      { path: "data/extraction/:taskId/result", element: <ExtractionResultPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
