import type { RouteObject } from "react-router-dom"

import { DocsPage } from "./DocsPage"

export const docsRoutes = (): RouteObject[] => [
    {
        path: "/docs",
        element: <DocsPage />,
    },
]
