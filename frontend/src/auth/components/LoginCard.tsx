import { useAuth } from '@/auth/hooks/useAuth';
import { GitHubIcon } from '@/components/icons/GitHubIcon';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export const LoginCard = () => {
  const { loginWithGithub } = useAuth();

  return (
    <div className="flex justify-center pt-20 px-4">
      <Card className="w-full max-w-md shadow-md border border-gray-200/60">
        <CardHeader className="space-y-2">
          <CardTitle className="text-center text-xl font-semibold">Sign In Required</CardTitle>
          <CardDescription className="text-center">
            You must be logged in to access this page.
          </CardDescription>
        </CardHeader>

        <CardContent className="pt-4">
          <Button onClick={loginWithGithub} className="w-full gap-2 font-medium">
            <GitHubIcon />
            Log in with GitHub
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
