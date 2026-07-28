import { Navigate, useLocation, useParams } from 'react-router-dom';

export const LegacyExecutionRedirect = () => {
  const { id } = useParams();
  const location = useLocation();
  const pathname = id ? `/executions/${id}` : '/executions';

  return (
    <Navigate
      replace
      state={location.state}
      to={`${pathname}${location.search}${location.hash}`}
    />
  );
};
