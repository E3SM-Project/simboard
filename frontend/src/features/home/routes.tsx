import type { RouteObject } from "react-router-dom"

import type { Machine, SimulationOut } from "@/types"

import { HomePage } from "./HomePage"

interface HomeRoutesProps {
    simulations: SimulationOut[]
    machines: Machine[]
}

export const homeRoutes = ({
    simulations,
    machines,
}: HomeRoutesProps): RouteObject[] => [
        {
            path: "/",
            element: (
                <HomePage
                    simulations={simulations}
                    machines={machines}
                />
            ),
        },
    ]
