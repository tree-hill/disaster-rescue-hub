import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Login } from '@/pages/Login';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/login" replace />,
  },
  {
    path: '/login',
    element: <Login />,
  },
]);
