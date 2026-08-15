import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, lazy } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { ToastProvider, ToastViewport } from "./components/ui/toast";
import { TooltipProvider } from "./components/ui/tooltip";
import { queryClient } from "./api/query-client";
import { router } from "./app/router";
import "./index.css";

// Devtools only in dev: the conditional import is tree-shaken out of the
// production bundle (keeps ~370 kB of dev-only code off the critical path).
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import("@tanstack/react-query-devtools").then((m) => ({
        default: m.ReactQueryDevtools,
      }))
    )
  : null;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <ToastViewport />
          {ReactQueryDevtools ? <ReactQueryDevtools initialIsOpen={false} /> : null}
        </QueryClientProvider>
      </ToastProvider>
    </TooltipProvider>
  </StrictMode>
);
