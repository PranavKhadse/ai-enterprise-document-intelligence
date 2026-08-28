import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { storage } from './utils/storage';

// Initialize Theme on startup
const initialTheme = storage.getTheme();
if (initialTheme === 'dark') {
  document.documentElement.classList.add('dark');
} else {
  document.documentElement.classList.remove('dark');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
