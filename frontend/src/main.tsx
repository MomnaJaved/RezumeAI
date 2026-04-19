import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./auth";
import { LanguageProvider } from "./i18n";
import { NotificationProvider } from "./notifications";
import { ToastProvider } from "./toast";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <ToastProvider>
            <NotificationProvider>
              <App />
            </NotificationProvider>
          </ToastProvider>
        </BrowserRouter>
      </AuthProvider>
    </LanguageProvider>
  </React.StrictMode>,
);
