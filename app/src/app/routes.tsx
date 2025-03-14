import * as React from 'react';
import { Route, RouteComponentProps, Switch, useLocation } from 'react-router-dom';
import { Dashboard } from '@app/Dashboard/Dashboard';
import { Mapping } from '@app/Mapping/Mapping';
import { NotFound } from '@app/NotFound/NotFound';
import { useDocumentTitle } from '@app/utils/useDocumentTitle';

let routeFocusTimer: number;
export interface IAppRoute {
  label?: string; // Excluding the label will exclude the route from the nav sidebar in AppLayout
  /* eslint-disable @typescript-eslint/no-explicit-any */
  component: React.ComponentType<RouteComponentProps<any>> | React.ComponentType<any>;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  exact?: boolean;
  path: string;
  title: string;
  routes?: undefined;
}

export interface IAppRouteGroup {
  label: string;
  routes: IAppRoute[];
}

export type AppRouteConfig = IAppRoute | IAppRouteGroup;
const api_id;
const routes: AppRouteConfig[] = [
  {
    component: Dashboard,
    exact: true,
    label: 'SW Components',
    path: '/',
    title: 'Basil | The Fusa Spice | Software Components',
  },
  {
    component: Mapping,
    exact: true,
    label: 'SW Specification Mapping',
    path: '/mapping/:api_id',
    title: 'Basil | The Fusa Spice | Software Component Specification Mapping',
  },
];

// a custom hook for sending focus to the primary content container
// after a view has loaded so that subsequent press of tab key
// sends focus directly to relevant content
// may not be necessary if https://github.com/ReactTraining/react-router/issues/5210 is resolved
const useA11yRouteChange = () => {
  const { pathname } = useLocation();
  React.useEffect(() => {
    routeFocusTimer = window.setTimeout(() => {
      const mainContainer = document.getElementById('primary-app-container');
      if (mainContainer) {
        mainContainer.focus();
      }
    }, 50);
    return () => {
      window.clearTimeout(routeFocusTimer);
    };
  }, [pathname]);
};

const RouteWithTitleUpdates = ({ component: Component, title, ...rest }: IAppRoute) => {
  useA11yRouteChange();
  useDocumentTitle(title);

  function routeWithTitle(routeProps: RouteComponentProps) {
    return <Component {...rest} {...routeProps} />;
  }

  return <Route render={routeWithTitle} {...rest} />;
};

const PageNotFound = ({ title }: { title: string }) => {
  useDocumentTitle(title);
  return <Route component={NotFound} />;
};

const flattenedRoutes: IAppRoute[] = routes.reduce(
  (flattened, route) => [...flattened, ...(route.routes ? route.routes : [route])],
  [] as IAppRoute[],
);

export interface AppRoutesProps {
  notificationCount;
  setNotificationCount;
}

const AppRoutes = ({
    notificationCount,
    setNotificationCount,
    }: AppRoutesProps): React.ReactElement => (
  <Switch>
    {flattenedRoutes.map(({ path, exact, component, title }, idx) => (
      <RouteWithTitleUpdates
        path={path}
        exact={exact}
        component={component}
        key={idx}
        title={title}
        notificationCount={notificationCount}
        setNotificationCount={setNotificationCount} />
    ))}
    <PageNotFound title="404 Page Not Found" />
  </Switch>
);

export { AppRoutes, routes };
