import type { RouteObject } from "react-router-dom"

import type { SimulationOut } from "@/types"

import { SimulationDetailsPage } from "./SimulationDetailsPage"
import { SimulationsPage } from "./SimulationsPage"

interface SimulationRoutesProps {
    simulations: SimulationOut[]
}

export const simulationsRoutes = ({
    simulations,
}: SimulationRoutesProps): RouteObject[] => [
        {
            path: "/simulations",
            element: <SimulationsPage simulations={simulations} />,
        },
        {
            path: "/simulations/:id",
            element: <SimulationDetailsPage />,
        },
    ]
