import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getConfig, updateConfig, testZohoConnection } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import type { AppConfig } from '@/types'
import { Loader2, Save, TestTube, CheckCircle2, XCircle } from 'lucide-react'

export default function Settings() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
  })

  const [formData, setFormData] = useState<Partial<AppConfig>>({})

  // Merge loaded config with form changes
  const currentConfig = { ...config, ...formData }

  const updateMutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      toast({ title: 'Settings Saved', description: 'Configuration updated successfully' })
      queryClient.invalidateQueries({ queryKey: ['config'] })
      setFormData({})
    },
    onError: (error: Error) => {
      toast({ title: 'Save Failed', description: error.message, variant: 'destructive' })
    },
  })

  const testMutation = useMutation({
    mutationFn: testZohoConnection,
    onSuccess: (result) => {
      setTestResult(result)
      if (result.success) {
        toast({ title: 'Connection Successful', description: result.message })
      } else {
        toast({ title: 'Connection Failed', description: result.message, variant: 'destructive' })
      }
    },
    onError: (error: Error) => {
      setTestResult({ success: false, message: error.message })
      toast({ title: 'Test Failed', description: error.message, variant: 'destructive' })
    },
  })

  const handleChange = (key: keyof AppConfig, value: string | number) => {
    setFormData((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = () => {
    if (Object.keys(formData).length > 0) {
      updateMutation.mutate(formData)
    }
  }

  const hasChanges = Object.keys(formData).length > 0

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
          <p className="text-muted-foreground">Configure Zoho Creator sync and image processing</p>
        </div>
        <Button onClick={handleSave} disabled={!hasChanges || updateMutation.isPending}>
          {updateMutation.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          Save Changes
        </Button>
      </div>

      <Tabs defaultValue="zoho" className="space-y-4">
        <TabsList>
          <TabsTrigger value="zoho">Zoho Connection</TabsTrigger>
          <TabsTrigger value="fields">Field Mappings</TabsTrigger>
          <TabsTrigger value="processing">Image Processing</TabsTrigger>
          <TabsTrigger value="sync">Sync Schedule</TabsTrigger>
        </TabsList>

        {/* Zoho Connection */}
        <TabsContent value="zoho">
          <Card>
            <CardHeader>
              <CardTitle>Zoho Creator Connection</CardTitle>
              <CardDescription>OAuth credentials and API configuration</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="zoho_client_id">Client ID</Label>
                  <Input
                    id="zoho_client_id"
                    type="password"
                    value={currentConfig.zoho_client_id || ''}
                    onChange={(e) => handleChange('zoho_client_id', e.target.value)}
                    placeholder="Enter Client ID"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zoho_client_secret">Client Secret</Label>
                  <Input
                    id="zoho_client_secret"
                    type="password"
                    value={currentConfig.zoho_client_secret || ''}
                    onChange={(e) => handleChange('zoho_client_secret', e.target.value)}
                    placeholder="Enter Client Secret"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="zoho_refresh_token">Refresh Token</Label>
                <Input
                  id="zoho_refresh_token"
                  type="password"
                  value={currentConfig.zoho_refresh_token || ''}
                  onChange={(e) => handleChange('zoho_refresh_token', e.target.value)}
                  placeholder="Enter Refresh Token"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="zoho_account_owner_name">Account Owner Name</Label>
                  <Input
                    id="zoho_account_owner_name"
                    value={currentConfig.zoho_account_owner_name || ''}
                    onChange={(e) => handleChange('zoho_account_owner_name', e.target.value)}
                    placeholder="username"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zoho_app_link_name">App Link Name</Label>
                  <Input
                    id="zoho_app_link_name"
                    value={currentConfig.zoho_app_link_name || ''}
                    onChange={(e) => handleChange('zoho_app_link_name', e.target.value)}
                    placeholder="my-app"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zoho_report_link_name">Report Link Name</Label>
                  <Input
                    id="zoho_report_link_name"
                    value={currentConfig.zoho_report_link_name || ''}
                    onChange={(e) => handleChange('zoho_report_link_name', e.target.value)}
                    placeholder="All_Photos"
                  />
                </div>
              </div>

              <div className="flex items-center gap-4 pt-4">
                <Button
                  variant="outline"
                  onClick={() => testMutation.mutate()}
                  disabled={testMutation.isPending}
                >
                  {testMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <TestTube className="mr-2 h-4 w-4" />
                  )}
                  Test Connection
                </Button>
                {testResult && (
                  <div className="flex items-center gap-2 text-sm">
                    {testResult.success ? (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-600" />
                    )}
                    <span className={testResult.success ? 'text-green-600' : 'text-red-600'}>
                      {testResult.message}
                    </span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Field Mappings */}
        <TabsContent value="fields">
          <Card>
            <CardHeader>
              <CardTitle>Field Mappings</CardTitle>
              <CardDescription>
                Map Zoho Creator form fields to sync categories. Use the exact field API names from your Zoho form.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="field_job_captain_timesheet">Job Captain Timesheet Field</Label>
                  <Input
                    id="field_job_captain_timesheet"
                    value={currentConfig.field_job_captain_timesheet || ''}
                    onChange={(e) => handleChange('field_job_captain_timesheet', e.target.value)}
                    placeholder="Add_Job_Captain_Time_Sheet_Number"
                  />
                  <p className="text-xs text-muted-foreground">
                    Field containing the Job Captain Timesheet number
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="field_project_name">Project Name Field</Label>
                  <Input
                    id="field_project_name"
                    value={currentConfig.field_project_name || ''}
                    onChange={(e) => handleChange('field_project_name', e.target.value)}
                    placeholder="Project"
                  />
                  <p className="text-xs text-muted-foreground">
                    Field containing the project name/number
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="field_department">Department Field</Label>
                  <Input
                    id="field_department"
                    value={currentConfig.field_department || ''}
                    onChange={(e) => handleChange('field_department', e.target.value)}
                    placeholder="Project_Department1"
                  />
                  <p className="text-xs text-muted-foreground">
                    Field containing the department name
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="field_tags">Tags Field (optional)</Label>
                  <Input
                    id="field_tags"
                    value={currentConfig.field_tags || ''}
                    onChange={(e) => handleChange('field_tags', e.target.value)}
                    placeholder="Tags"
                  />
                  <p className="text-xs text-muted-foreground">
                    Field for additional tags/keywords
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="field_description">Description Field (optional)</Label>
                <Input
                  id="field_description"
                  value={currentConfig.field_description || ''}
                  onChange={(e) => handleChange('field_description', e.target.value)}
                  placeholder="Description"
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Image Processing */}
        <TabsContent value="processing">
          <Card>
            <CardHeader>
              <CardTitle>Image Processing</CardTitle>
              <CardDescription>Configure how images are optimized during sync</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Size Threshold (MB)</Label>
                  <span className="text-sm font-medium">{currentConfig.image_max_size_mb || 5} MB</span>
                </div>
                <Slider
                  value={[currentConfig.image_max_size_mb || 5]}
                  onValueChange={([val]) => handleChange('image_max_size_mb', val)}
                  min={1}
                  max={20}
                  step={1}
                />
                <p className="text-xs text-muted-foreground">
                  Images larger than this will be processed and optimized
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Max Dimension (pixels)</Label>
                  <span className="text-sm font-medium">{currentConfig.image_max_dimension || 4000} px</span>
                </div>
                <Slider
                  value={[currentConfig.image_max_dimension || 4000]}
                  onValueChange={([val]) => handleChange('image_max_dimension', val)}
                  min={1000}
                  max={8000}
                  step={500}
                />
                <p className="text-xs text-muted-foreground">
                  Maximum width/height for processed images (maintains aspect ratio)
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>WebP Quality</Label>
                  <span className="text-sm font-medium">{currentConfig.image_quality || 85}%</span>
                </div>
                <Slider
                  value={[currentConfig.image_quality || 85]}
                  onValueChange={([val]) => handleChange('image_quality', val)}
                  min={50}
                  max={100}
                  step={5}
                />
                <p className="text-xs text-muted-foreground">
                  Higher quality = larger file size. 85% is recommended for most cases.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Sync Schedule */}
        <TabsContent value="sync">
          <Card>
            <CardHeader>
              <CardTitle>Sync Schedule</CardTitle>
              <CardDescription>Configure automatic sync timing</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="sync_cron">Cron Expression</Label>
                <Input
                  id="sync_cron"
                  value={currentConfig.sync_cron || '0 2 * * *'}
                  onChange={(e) => handleChange('sync_cron', e.target.value)}
                  placeholder="0 2 * * *"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground">
                  Default: "0 2 * * *" (2:00 AM daily). Format: minute hour day month weekday
                </p>
              </div>

              <div className="rounded-md bg-muted p-4">
                <p className="text-sm font-medium">Common schedules:</p>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  <li><code className="rounded bg-background px-1">0 2 * * *</code> - Daily at 2 AM</li>
                  <li><code className="rounded bg-background px-1">0 */6 * * *</code> - Every 6 hours</li>
                  <li><code className="rounded bg-background px-1">0 0 * * 0</code> - Weekly on Sunday</li>
                  <li><code className="rounded bg-background px-1">*/30 * * * *</code> - Every 30 minutes</li>
                </ul>
              </div>

              <div className="space-y-2">
                <Label htmlFor="supabase_storage_bucket">Storage Bucket</Label>
                <Input
                  id="supabase_storage_bucket"
                  value={currentConfig.supabase_storage_bucket || 'zoho-pictures'}
                  onChange={(e) => handleChange('supabase_storage_bucket', e.target.value)}
                  placeholder="zoho-pictures"
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
