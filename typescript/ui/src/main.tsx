import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import '@xyflow/react/dist/style.css';
import './globals.css';
import { ThemeProvider } from './components/providers/ThemeProvider';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
