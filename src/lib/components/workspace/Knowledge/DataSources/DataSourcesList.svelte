<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import CreateDataSourceModal from './CreateDataSourceModal.svelte';
	import {
		getDataSourcesByKnowledgeId,
		syncDataSource,
		updateDataSource,
		deleteDataSource,
		type DataSource
	} from '$lib/apis/data_sources';
	import { isValidCronExpression } from '$lib/utils/cron';

	export let knowledgeId: string;
	export let writeAccess: boolean = false;

	let loading = true;
	let dataSources: DataSource[] = [];
	let showCreateModal = false;
	let showDetailsModal = false;
	let selectedDataSource: DataSource | null = null;
	let selectedSyncMode = 'manual';
	let customCronExpression = '';
	let savingSchedule = false;
	let syncingById: Record<string, boolean> = {};
	let deletingById: Record<string, boolean> = {};
	let showCronValidation = false;

	onMount(async () => {
		await loadDataSources();
	});

	export function openCreateModal() {
		showCreateModal = true;
	}

	async function loadDataSources() {
		loading = true;
		try {
			const result = await getDataSourcesByKnowledgeId(localStorage.token, knowledgeId);
			dataSources = result.items;
		} catch (e) {
			toast.error(`Failed to load data sources: ${e}`);
		} finally {
			loading = false;
		}
	}

	function handleCreated(event: CustomEvent) {
		dataSources = [event.detail, ...dataSources];
		dispatch('changed');
	}

	function handleDeleted(event: CustomEvent) {
		const deletedId = event.detail as string;
		dataSources = dataSources.filter((ds) => ds.id !== deletedId);
		if (selectedDataSource?.id === deletedId) {
			closeDetails();
		}
		dispatch('changed');
	}

	function openDetails(dataSource: DataSource) {
		selectedDataSource = dataSource;
		selectedSyncMode = (dataSource.sync_config?.sync_mode as string) || 'manual';
		customCronExpression = (dataSource.sync_config?.cron as string) || '';
		showCronValidation = false;
		showDetailsModal = true;
	}

	function closeDetails() {
		showDetailsModal = false;
	}

	$: if (!showDetailsModal && selectedDataSource) {
		selectedDataSource = null;
	}

	$: if (selectedDataSource) {
		const updated = dataSources.find((ds) => ds.id === selectedDataSource?.id);
		if (!updated) {
			closeDetails();
		} else if (updated !== selectedDataSource) {
			selectedDataSource = updated;
		}
	}

	function formatTimestamp(timestamp: number | null): string {
		if (!timestamp) return 'Never';
		const date = new Date(timestamp * 1000);
		return date.toLocaleString();
	}

	const syncIntervalSeconds: Record<string, number> = {
		hourly: 60 * 60,
		every_6_hours: 6 * 60 * 60,
		every_12_hours: 12 * 60 * 60,
		daily: 24 * 60 * 60,
		weekly: 7 * 24 * 60 * 60
	};

	function getNextSyncLabel(dataSource: DataSource): string {
		const syncMode = (dataSource.sync_config?.sync_mode as string) || 'manual';
		const intervalSeconds = syncIntervalSeconds[syncMode];

		if (syncMode === 'custom') {
			const cron = dataSource.sync_config?.cron as string | undefined;
			return cron ? $i18n.t('Scheduled by cron: {{cron}}', { cron }) : $i18n.t('Custom schedule');
		}

		if (!intervalSeconds) {
			return $i18n.t('Manual only');
		}

		if (!dataSource.last_sync_at) {
			return $i18n.t('Pending');
		}

		return formatTimestamp(dataSource.last_sync_at + intervalSeconds);
	}

	function getSyncModeLabel(mode: string): string {
		const labels: Record<string, string> = {
			manual: 'Manual',
			hourly: 'Hourly',
			every_6_hours: 'Every 6 hours',
			every_12_hours: 'Every 12 hours',
			daily: 'Daily',
			weekly: 'Weekly',
			custom: 'Custom'
		};
		return labels[mode] || mode;
	}

	function getStatusTextClass(status: string): string {
		switch (status) {
			case 'syncing':
				return 'text-blue-600 dark:text-blue-400';
			case 'error':
				return 'text-red-600 dark:text-red-400';
			default:
				return 'text-green-600 dark:text-green-400';
		}
	}

	function getStatusDotClass(status: string): string {
		switch (status) {
			case 'syncing':
				return 'bg-blue-500';
			case 'error':
				return 'bg-red-500';
			default:
				return 'bg-green-500';
		}
	}

	function getSourceTypeIcon(typeId: string): string {
		const icons: Record<string, string> = {
			confluence:
				'M2.5 19.7c-.2-.4-.1-.9.2-1.2l6.4-8.5c.1-.1.1-.3 0-.4L3.4 2.2c-.3-.3-.4-.8-.2-1.2.2-.4.6-.6 1-.6h5.3c.4 0 .7.2.9.5l5.5 7.5c.1.2.4.2.5 0l5.5-7.5c.2-.3.5-.5.9-.5h5.3c.4 0 .8.2 1 .6.2.4.1.9-.2 1.2l-5.7 7.4c-.1.1-.1.3 0 .4l6.4 8.5c.3.3.4.8.2 1.2-.2.4-.6.6-1 .6h-5.3c-.4 0-.7-.2-.9-.5l-6.1-8.2c-.1-.2-.4-.2-.5 0l-6.1 8.2c-.2.3-.5.5-.9.5H3.5c-.4 0-.8-.2-1-.6z',
			jira: 'M11.53.69a2.19 2.19 0 0 1 .94 0l9.63 2.25a2.2 2.2 0 0 1 1.67 2.12v9.88a2.2 2.2 0 0 1-1.67 2.12l-9.63 2.25a2.19 2.19 0 0 1-.94 0l-9.63-2.25A2.2 2.2 0 0 1 .23 14.94V5.06a2.2 2.2 0 0 1 1.67-2.12L11.53.69z',
			github:
				'M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z'
		};
		return icons[typeId] || '';
	}

	async function handleSync(dataSource: DataSource) {
		if (syncingById[dataSource.id]) {
			return;
		}

		syncingById = { ...syncingById, [dataSource.id]: true };
		try {
			const result = await syncDataSource(localStorage.token, dataSource.id);
			if (result.success) {
				toast.success(
					$i18n.t('Sync completed: {{count}} files synced', { count: result.files_synced })
				);
				await loadDataSources();
				dispatch('changed');
			} else {
				toast.error($i18n.t('Sync failed'));
			}
		} catch (e) {
			toast.error(`Sync failed: ${e}`);
		} finally {
			syncingById = { ...syncingById, [dataSource.id]: false };
		}
	}

	async function handleSaveSchedule() {
		if (!selectedDataSource) return;
		savingSchedule = true;
		try {
			const trimmedCron = customCronExpression.trim();
			if (selectedSyncMode === 'custom') {
				showCronValidation = true;
				if (!isValidCronExpression(trimmedCron)) {
					return;
				}
			}

			const syncConfig: Record<string, unknown> = {
				sync_mode: selectedSyncMode
			};
			if (selectedSyncMode === 'custom') {
				syncConfig.cron = trimmedCron;
			}

			const updated = await updateDataSource(localStorage.token, selectedDataSource.id, {
				sync_config: syncConfig
			});
			dataSources = dataSources.map((ds) => (ds.id === updated.id ? updated : ds));
			selectedDataSource = updated;
			selectedSyncMode = (updated.sync_config?.sync_mode as string) || 'manual';
			customCronExpression = (updated.sync_config?.cron as string) || '';
			dispatch('changed');
			toast.success($i18n.t('Sync schedule updated'));
		} catch (e) {
			toast.error(`Failed to update sync schedule: ${e}`);
		} finally {
			savingSchedule = false;
		}
	}

	async function handleDelete(dataSource: DataSource) {
		if (!confirm($i18n.t('Are you sure you want to delete this data source?'))) {
			return;
		}

		deletingById = { ...deletingById, [dataSource.id]: true };
		try {
			await deleteDataSource(localStorage.token, dataSource.id);
			dataSources = dataSources.filter((ds) => ds.id !== dataSource.id);
			dispatch('changed');
			toast.success($i18n.t('Data source deleted'));
			closeDetails();
		} catch (e) {
			toast.error(`Failed to delete: ${e}`);
		} finally {
			deletingById = { ...deletingById, [dataSource.id]: false };
		}
	}
</script>

<CreateDataSourceModal
	bind:show={showCreateModal}
	{knowledgeId}
	on:created={handleCreated}
/>

<div class="space-y-3">
	<!-- Content -->
	{#if loading}
		<div class="flex justify-center py-8">
			<Spinner className="size-5" />
		</div>
	{:else if dataSources.length === 0}
		<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
			<span>{$i18n.t('No external data sources connected')}</span>
			{#if writeAccess}
				<button
					class="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
					on:click={openCreateModal}
				>
					{$i18n.t('Connect a data source')}
				</button>
			{/if}
		</div>
	{:else}
		<div class="flex flex-wrap gap-2">
			{#each dataSources as dataSource (dataSource.id)}
				<div
					class="inline-flex items-center gap-1.5 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50/80 dark:bg-gray-850/70"
				>
					<button
						class="flex items-center gap-2 pl-2.5 pr-2 py-1.5 text-sm"
						on:click={() => openDetails(dataSource)}
					>
						<span
							class="flex size-6 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-200"
						>
							<svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
								<path d={getSourceTypeIcon(dataSource.source_type)} />
							</svg>
						</span>
						<span class="font-medium">{dataSource.name}</span>
						<span class="inline-flex items-center gap-1 text-xs">
							{#if dataSource.status === 'syncing'}
								<Spinner className="size-3" />
								<span class={getStatusTextClass(dataSource.status)}>
									{$i18n.t('Syncing')}
								</span>
							{:else}
								<span class="h-1.5 w-1.5 rounded-full {getStatusDotClass(dataSource.status)}" />
								<span class="capitalize {getStatusTextClass(dataSource.status)}">
									{dataSource.status}
								</span>
							{/if}
						</span>
					</button>

					{#if writeAccess}
						<div class="pr-1.5">
							<Tooltip content={$i18n.t('Sync now')}>
								<button
									class="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed"
									disabled={syncingById[dataSource.id] || dataSource.status === 'syncing'}
									on:click|stopPropagation={() => handleSync(dataSource)}
								>
									{#if syncingById[dataSource.id]}
										<Spinner className="size-3" />
									{:else}
										<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
											/>
										</svg>
									{/if}
								</button>
							</Tooltip>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if selectedDataSource}
	<Modal size="md" bind:show={showDetailsModal}>
		<div class="px-6 py-5 space-y-5">
			<div class="flex items-start justify-between gap-4">
				<div class="min-w-0">
					<h2 class="text-lg font-semibold truncate">{selectedDataSource.name}</h2>
					<div class="mt-1 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
						<span class="capitalize">{selectedDataSource.source_type}</span>
						<span>•</span>
						<span class="inline-flex items-center gap-1">
							{#if selectedDataSource.status === 'syncing'}
								<Spinner className="size-3" />
								<span class={getStatusTextClass(selectedDataSource.status)}>
									{$i18n.t('Syncing')}
								</span>
							{:else}
								<span
									class="h-1.5 w-1.5 rounded-full {getStatusDotClass(
										selectedDataSource.status
									)}"
								/>
								<span class="capitalize {getStatusTextClass(selectedDataSource.status)}">
									{selectedDataSource.status}
								</span>
							{/if}
						</span>
					</div>
				</div>
				<button
					class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
					on:click={closeDetails}
				>
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div class="grid gap-3 text-sm">
				<div class="flex items-center justify-between">
					<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Last sync')}</span>
					<span>{formatTimestamp(selectedDataSource.last_sync_at)}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Next sync')}</span>
					<span>{getNextSyncLabel(selectedDataSource)}</span>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Sync Schedule')}</span>
					<span>{getSyncModeLabel(selectedDataSource.sync_config?.sync_mode || 'manual')}</span>
				</div>
			</div>

			{#if selectedDataSource.status === 'error' && selectedDataSource.last_sync_error}
				<div class="p-3 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-600 dark:text-red-400">
					{selectedDataSource.last_sync_error}
				</div>
			{/if}

			<div class="space-y-3">
				<div>
					<label class="block text-sm font-medium mb-2">{$i18n.t('Sync Schedule')}</label>
					<select
						class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						bind:value={selectedSyncMode}
					>
						<option value="manual">{$i18n.t('Manual only')}</option>
						<option value="hourly">{$i18n.t('Every hour')}</option>
						<option value="every_6_hours">{$i18n.t('Every 6 hours')}</option>
						<option value="every_12_hours">{$i18n.t('Every 12 hours')}</option>
						<option value="daily">{$i18n.t('Daily')}</option>
						<option value="weekly">{$i18n.t('Weekly')}</option>
						<option value="custom">{$i18n.t('Custom (cron)')}</option>
					</select>
					{#if selectedSyncMode === 'custom'}
						<div class="mt-3 space-y-2">
							<label class="block text-xs font-medium text-gray-500 dark:text-gray-400">
								{$i18n.t('Cron expression')}
							</label>
							<input
								class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
								bind:value={customCronExpression}
								placeholder="* 2 * * *"
								on:input={() => (showCronValidation = true)}
							/>
							{#if showCronValidation && !isValidCronExpression(customCronExpression)}
								<p class="text-xs text-red-600 dark:text-red-400">
									{$i18n.t('Cron syntax is invalid.')}
								</p>
							{/if}
							<p class="text-xs text-gray-500">
								{$i18n.t('Format: minute hour day-of-month month day-of-week')}
							</p>
						</div>
					{/if}
				</div>

				<div class="flex justify-end">
					<button
						class="px-3 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={savingSchedule || (selectedSyncMode === 'custom' && !isValidCronExpression(customCronExpression))}
						on:click={handleSaveSchedule}
					>
						{#if savingSchedule}
							<Spinner className="size-4" />
						{:else}
							{$i18n.t('Save')}
						{/if}
					</button>
				</div>
			</div>

			{#if writeAccess}
				<div class="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-800">
					<button
						class="px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
						disabled={syncingById[selectedDataSource.id] || selectedDataSource.status === 'syncing'}
						on:click={() => handleSync(selectedDataSource)}
					>
						{#if syncingById[selectedDataSource.id]}
							<Spinner className="size-4" />
						{:else}
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
								/>
							</svg>
						{/if}
						{$i18n.t('Sync now')}
					</button>
					<button
						class="px-3 py-2 text-sm rounded-lg text-red-600 border border-red-200 hover:bg-red-50 dark:border-red-900/40 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
						disabled={deletingById[selectedDataSource.id]}
						on:click={() => handleDelete(selectedDataSource)}
					>
						{#if deletingById[selectedDataSource.id]}
							<Spinner className="size-4" />
						{:else}
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
								/>
							</svg>
						{/if}
						{$i18n.t('Delete')}
					</button>
				</div>
			{/if}
		</div>
	</Modal>
{/if}
