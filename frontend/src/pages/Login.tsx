import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/store/auth'
import { LogIn, AlertCircle, Loader2 } from 'lucide-react'

export default function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { isAuthenticated, isLoading, checkAuth } = useAuthStore()

  // Get error from URL params (set by OAuth callback)
  const error = searchParams.get('error')
  const errorMessage = searchParams.get('message')

  useEffect(() => {
    // Check if already authenticated
    checkAuth().then((authenticated) => {
      if (authenticated) {
        navigate('/', { replace: true })
      }
    })
  }, [checkAuth, navigate])

  const handleLogin = () => {
    // Redirect to backend OAuth login endpoint
    window.location.href = '/api/auth/login'
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    )
  }

  if (isAuthenticated) {
    return null // Will redirect via useEffect
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Zoho Pictures Sync</CardTitle>
          <CardDescription>
            Sign in with your Zoho account to access the application
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
              <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Authentication Failed</p>
                <p className="text-sm mt-1 text-red-700">
                  {errorMessage || getErrorDescription(error)}
                </p>
              </div>
            </div>
          )}

          <Button
            onClick={handleLogin}
            className="w-full"
            size="lg"
          >
            <LogIn className="mr-2 h-5 w-5" />
            Sign in with Zoho
          </Button>

          <p className="text-center text-sm text-slate-500">
            Only authorized users can access this application.
            Contact your administrator if you need access.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function getErrorDescription(error: string): string {
  switch (error) {
    case 'access_denied':
      return 'Your account is not authorized to access this application.'
    case 'invalid_state':
      return 'The login request was invalid. Please try again.'
    case 'token_error':
      return 'Failed to complete authentication. Please try again.'
    case 'server_error':
      return 'A server error occurred. Please try again later.'
    default:
      return 'An error occurred during authentication. Please try again.'
  }
}
