import React from 'react';
import ReactDOM from 'react-dom/client';
import '@mantine/core/styles.css';
import { MantineProvider, createTheme } from '@mantine/core';
import App from './App';
import '@xyflow/react/dist/style.css';
import './globals.css';
import { ThemeProvider } from './components/providers/ThemeProvider';

const mantineTheme = createTheme({
  primaryColor: 'teal',
  defaultRadius: 'md',
  fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  fontFamilyMonospace: 'ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, monospace',
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <MantineProvider defaultColorScheme="dark" theme={mantineTheme}>
        <App />
      </MantineProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
