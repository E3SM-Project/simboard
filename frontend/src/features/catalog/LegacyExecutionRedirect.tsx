import { Navigate, useLocation } from 'react-router-dom';

export const LegacyExecutionRedirect = () => {
  const location = useLocation();

  return (
    <Navigate
      replace
      state={location.state}
      to={`/executions${location.search}${location.hash}`}
    />
  );
};
