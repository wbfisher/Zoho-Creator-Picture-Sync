import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Image, Settings, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { getStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/gallery', icon: Image, label: 'Gallery' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout() {
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: 5000,
  })

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-bold">Zoho Picture Sync</h1>
            <nav className="flex items-center gap-1">
              {navItems.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
                      isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'
                    )
                  }
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>

          {/* Sync Status Indicator */}
          <div className="flex items-center gap-2 text-sm">
            {status?.is_running ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin text-yellow-500" />
                <span className="text-yellow-600">Syncing...</span>
              </>
            ) : (
              <>
                <div className="h-2 w-2 rounded-full bg-green-500" />
                <span className="text-muted-foreground">
                  {status?.stats.total_images.toLocaleString() ?? '-'} images
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-6">
        <Outlet />
      </main>
    </div>
  )
}
