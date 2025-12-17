import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getStatus, getSyncRuns, triggerSync } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'
import { formatDate, formatRelativeTime } from '@/lib/utils'
import {
  Image,
  Sparkles,
  Clock,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Loader2,
} from 'lucide-react'

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['status'],
    queryFn: getStatus,
    refetchInterval: 5000,
  })

  const { data: runs } = useQuery({
    queryKey: ['runs'],
    queryFn: () => getSyncRuns(10),
    refetchInterval: 10000,
  })

  const syncMutation = useMutation({
    mutationFn: ({ fullSync, maxRecords }: { fullSync: boolean; maxRecords?: number }) =>
      triggerSync(fullSync, maxRecords),
    onSuccess: (data) => {
      const desc = data.max_records
        ? `${data.message} (limited to ${data.max_records} records)`
        : data.message
      toast({ title: 'Sync Started', description: desc })
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
    onError: (error: Error) => {
      toast({ title: 'Sync Failed', description: error.message, variant: 'destructive' })
    },
  })

  const getStatusBadge = (runStatus: string) => {
    switch (runStatus) {
      case 'running':
        return <Badge variant="warning"><Loader2 className="mr-1 h-3 w-3 animate-spin" /> Running</Badge>
      case 'completed':
        return <Badge variant="success"><CheckCircle2 className="mr-1 h-3 w-3" /> Completed</Badge>
      case 'completed_with_errors':
        return <Badge variant="warning"><AlertCircle className="mr-1 h-3 w-3" /> With Errors</Badge>
      case 'failed':
        return <Badge variant="destructive"><XCircle className="mr-1 h-3 w-3" /> Failed</Badge>
      default:
        return <Badge variant="secondary">{runStatus}</Badge>
    }
  }

  const lastSuccessfulRun = runs?.find(r => r.status === 'completed')

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Images</CardTitle>
            <Image className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statusLoading ? '-' : status?.stats.total_images.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">Synced from Zoho Creator</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Optimized</CardTitle>
            <Sparkles className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statusLoading ? '-' : status?.stats.processed_images.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">Converted to WebP</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Last Sync</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {lastSuccessfulRun ? formatRelativeTime(lastSuccessfulRun.completed_at) : '-'}
            </div>
            <p className="text-xs text-muted-foreground">
              {lastSuccessfulRun ? formatDate(lastSuccessfulRun.completed_at) : 'No syncs yet'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Sync Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Sync Actions</CardTitle>
          <CardDescription>
            Manually trigger a sync to import new or updated images from Zoho Creator
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            onClick={() => syncMutation.mutate({ fullSync: false, maxRecords: 10 })}
            disabled={syncMutation.isPending || status?.is_running}
          >
            <Play className="mr-2 h-4 w-4" />
            Test Sync (10 records)
          </Button>
          <Button
            onClick={() => syncMutation.mutate({ fullSync: false })}
            disabled={syncMutation.isPending || status?.is_running}
          >
            {status?.is_running ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-4 w-4" />
                Incremental Sync
              </>
            )}
          </Button>
          <Button
            variant="secondary"
            onClick={() => syncMutation.mutate({ fullSync: true })}
            disabled={syncMutation.isPending || status?.is_running}
          >
            <Play className="mr-2 h-4 w-4" />
            Full Sync
          </Button>
        </CardContent>
      </Card>

      {/* Recent Runs */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Sync Runs</CardTitle>
          <CardDescription>History of sync operations</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left">Started</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-right">Records</th>
                  <th className="px-4 py-3 text-right">Synced</th>
                  <th className="px-4 py-3 text-right">Skipped</th>
                  <th className="px-4 py-3 text-right">Errors</th>
                  <th className="px-4 py-3 text-right">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {runs?.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      No sync runs yet
                    </td>
                  </tr>
                )}
                {runs?.map((run) => {
                  const duration =
                    run.completed_at && run.started_at
                      ? Math.round(
                          (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000
                        )
                      : null
                  return (
                    <tr key={run.id} className="hover:bg-muted/50">
                      <td className="px-4 py-3">{formatDate(run.started_at)}</td>
                      <td className="px-4 py-3">{getStatusBadge(run.status)}</td>
                      <td className="px-4 py-3 text-right">{run.records_processed.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-medium text-green-600">
                        {run.images_synced.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right text-muted-foreground">
                        {run.images_skipped.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {run.errors > 0 ? (
                          <span className="text-red-600">{run.errors}</span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-muted-foreground">
                        {duration !== null ? `${duration}s` : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
