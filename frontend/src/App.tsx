/** Own the sole browser router and identity provider. */
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './features/auth/AuthProvider';
import { AppRoutes } from './routes';
/** Compose routing and auth without duplicate providers or route trees. */
export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider><AppRoutes /></AuthProvider>
    </BrowserRouter>
  );
}
