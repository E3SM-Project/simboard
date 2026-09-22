import type { RouteObject } from 'react-router-dom';

import { AboutPage } from '@/features/about/AboutPage';

export const aboutRoutes = (): RouteObject[] => [{ path: '/about', element: <AboutPage /> }];
