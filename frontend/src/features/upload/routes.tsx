import type { RouteObject } from "react-router-dom"

import { UploadPage } from "@/features/upload/UploadPage"
import type { Machine } from "@/types"

interface UploadRoutesProps {
    machines: Machine[]
}

export const uploadRoutes = ({
    machines,
}: UploadRoutesProps): RouteObject[] => [
        {
            path: "/upload",
            element: <UploadPage machines={machines} />,
        },
    ]
