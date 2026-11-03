// Browser entry point: index.html loads this file when the page opens.
// It connects React to the empty <div id="root"> and renders App inside it.
// The page layout lives in App.jsx; fetching and polling live in useDesks.js.

import { createRoot } from 'react-dom/client';
import App from './App';

// Mount the app in the root element from index.html.
createRoot(document.getElementById('root')).render(<App />);
