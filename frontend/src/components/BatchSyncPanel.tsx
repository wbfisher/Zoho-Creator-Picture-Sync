import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getBatchSyncStatus,
  startBatchSync,
  pauseBatchSync,
  resumeBatchSync,
  cancelBatchSync,
} from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { useToast } from '@/hooks/use-toast'
import { formatDate, formatRelativeTime } from '@/lib/utils'
import type { BatchSyncConfig, BatchSyncState } from '@/types'
import {
  Play,
  Pause,
  Square,
  Loader2,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Clock,
  Layers,
  Image,
  AlertTriangle,
} from 'lucide-react'

export function BatchSyncPanel() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Config state
  const [batchSize, setBatchSize] = useState(100)
  const [delaySeconds, setDelaySeconds] = useState(2)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [dryRun, setDryRun] = useState(false)

  // Fetch batch sync status
  const { data: batchStatus } = useQuery({
    queryKey: ['batchSyncStatus'],
    queryFn: getBatchSyncStatus,
    refetchInterval: 2000, // Poll every 2 seconds
  })

  const active = batchStatus?.active

  // Mutations
  const startMutation = useMutation({
    mutationFn: (config: BatchSyncConfig) => startBatchSync(config),
    onSuccess: (data) => {
      toast({ title: 'Batch Sync Started', description: data.message })
      queryClient.invalidateQueries({ queryKey: ['batchSyncStatus'] })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to Start', description: error.message, variant: 'destructive' })
    },
  })

  const pauseMutation = useMutation({
    mutationFn: (batchId: string) => pauseBatchSync(batchId),
    onSuccess: () => {
      toast({ title: 'Pause Requested', description: 'Sync will pause after current batch' })
      queryClient.invalidateQueries({ queryKey: ['batchSyncStatus'] })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to Pause', description: error.message, variant: 'destructive' })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: (batchId: string) => resumeBatchSync(batchId),
    onSuccess: () => {
      toast({ title: 'Batch Sync Resumed' })
      queryClient.invalidateQueries({ queryKey: ['batchSyncStatus'] })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to Resume', description: error.message, variant: 'destructive' })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (batchId: string) => cancelBatchSync(batchId),
    onSuccess: () => {
      toast({ title: 'Batch Sync Cancelled' })
      queryClient.invalidateQueries({ queryKey: ['batchSyncStatus'] })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to Cancel', description: error.message, variant: 'destructive' })
    },
  })

  const handleStart = () => {
    startMutation.mutate({
      batch_size: batchSize,
      delay_between_batches: delaySeconds,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      dry_run: dryRun,
    })
  }

  const getStatusBadge = (status: BatchSyncState['status']) => {
    switch (status) {
      case 'pending':
        return <Badge variant="secondary"><Clock className="mr-1 h-3 w-3" /> Pending</Badge>
      case 'running':
        return <Badge variant="warning"><Loader2 className="mr-1 h-3 w-3 animate-spin" /> Running</Badge>
      case 'paused':
        return <Badge variant="secondary"><Pause className="mr-1 h-3 w-3" /> Paused</Badge>
      case 'completed':
        return <Badge variant="success"><CheckCircle2 className="mr-1 h-3 w-3" /> Completed</Badge>
      case 'completed_with_errors':
        return <Badge variant="warning"><AlertCircle className="mr-1 h-3 w-3" /> With Errors</Badge>
      case 'cancelled':
        return <Badge variant="secondary"><Square className="mr-1 h-3 w-3" /> Cancelled</Badge>
      case 'failed':
        return <Badge variant="destructive"><XCircle className="mr-1 h-3 w-3" /> Failed</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const isRunning = active?.status === 'running'
  const isPaused = active?.status === 'paused'
  const canStart = !active || !['pending', 'running', 'paused'].includes(active.status)

  // Calculate progress percentage
  const progressPercent = active?.total_records_estimated && active.records_processed
    ? Math.min(100, Math.round((active.records_processed / active.total_records_estimated) * 100))
    : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Layers className="h-5 w-5" />
          Batch Sync
        </CardTitle>
        <CardDescription>
          Manageable sync with configurable batch sizes, pausing, and resume capability
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Active Batch Sync Status */}
        {active && ['pending', 'running', 'paused'].includes(active.status) && (
          <div className="rounded-lg border bg-muted/30 p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {getStatusBadge(active.status)}
                {active.dry_run && (
                  <Badge variant="outline">Dry Run</Badge>
                )}
              </div>
              <div className="flex items-center gap-2">
                {isRunning && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => pauseMutation.mutate(active.id)}
                    disabled={pauseMutation.isPending}
                  >
                    <Pause className="mr-1 h-4 w-4" />
                    Pause
                  </Button>
                )}
                {isPaused && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resumeMutation.mutate(active.id)}
                    disabled={resumeMutation.isPending}
                  >
                    <Play className="mr-1 h-4 w-4" />
                    Resume
                  </Button>
                )}
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => cancelMutation.mutate(active.id)}
                  disabled={cancelMutation.isPending}
                >
                  <Square className="mr-1 h-4 w-4" />
                  Cancel
                </Button>
              </div>
            </div>

            {/* Progress */}
            {progressPercent !== null && (
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span>Progress</span>
                  <span>{progressPercent}%</span>
                </div>
                <Progress value={progressPercent} />
              </div>
            )}

            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div className="space-y-1">
                <div className="text-muted-foreground">Batches</div>
                <div className="font-medium">{active.batches_completed}</div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground">Records</div>
                <div className="font-medium">
                  {active.records_processed.toLocaleString()}
                  {active.total_records_estimated && (
                    <span className="text-muted-foreground"> / {active.total_records_estimated.toLocaleString()}</span>
                  )}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground flex items-center gap-1">
                  <Image className="h-3 w-3" /> Synced
                </div>
                <div className="font-medium text-green-600">{active.images_synced.toLocaleString()}</div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> Errors
                </div>
                <div className={`font-medium ${active.errors > 0 ? 'text-red-600' : ''}`}>
                  {active.errors}
                </div>
              </div>
            </div>

            {/* Timing */}
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>Started: {formatRelativeTime(active.created_at)}</span>
              {active.last_batch_completed_at && (
                <span>Last batch: {formatRelativeTime(active.last_batch_completed_at)}</span>
              )}
            </div>
          </div>
        )}

        {/* Configuration Form */}
        {canStart && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="batchSize">Batch Size</Label>
                <Input
                  id="batchSize"
                  type="number"
                  min={10}
                  max={500}
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">Records per batch (10-500)</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="delaySeconds">Delay Between Batches</Label>
                <Input
                  id="delaySeconds"
                  type="number"
                  min={0}
                  max={60}
                  value={delaySeconds}
                  onChange={(e) => setDelaySeconds(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">Seconds to wait (0-60)</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="dateFrom">Date From (optional)</Label>
                <Input
                  id="dateFrom"
                  type="datetime-local"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dateTo">Date To (optional)</Label>
                <Input
                  id="dateTo"
                  type="datetime-local"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="dryRun"
                checked={dryRun}
                onCheckedChange={(checked) => setDryRun(checked === true)}
              />
              <Label htmlFor="dryRun" className="text-sm font-normal">
                Dry run (preview only, no actual sync)
              </Label>
            </div>

            <Button
              onClick={handleStart}
              disabled={startMutation.isPending}
              className="w-full"
            >
              {startMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Start Batch Sync
                </>
              )}
            </Button>
          </div>
        )}

        {/* Recent Batch Syncs */}
        {batchStatus?.recent && batchStatus.recent.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Recent Batch Syncs</h4>
            <div className="space-y-2">
              {batchStatus.recent.slice(0, 3).map((batch) => (
                <div
                  key={batch.id}
                  className="flex items-center justify-between rounded border p-2 text-sm"
                >
                  <div className="flex items-center gap-2">
                    {getStatusBadge(batch.status)}
                    <span className="text-muted-foreground">{formatDate(batch.created_at)}</span>
                  </div>
                  <div className="flex items-center gap-4 text-muted-foreground">
                    <span>{batch.records_processed.toLocaleString()} records</span>
                    <span className="text-green-600">{batch.images_synced.toLocaleString()} synced</span>
                    {batch.errors > 0 && (
                      <span className="text-red-600">{batch.errors} errors</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
