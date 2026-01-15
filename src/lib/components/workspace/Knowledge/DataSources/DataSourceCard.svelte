<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { syncDataSource, deleteDataSource, type DataSource } from '$lib/apis/data_sources';

	export let dataSource: DataSource;
	export let writeAccess: boolean = false;

	let syncing = false;
	let deleting = false;

	function formatTimestamp(timestamp: number | null): string {
		if (!timestamp) return 'Never';
		const date = new Date(timestamp * 1000);
		return date.toLocaleString();
	}

	function getSyncModeLabel(mode: string): string {
		const labels: Record<string, string> = {
			manual: 'Manual',
			hourly: 'Hourly',
			every_6_hours: 'Every 6 hours',
			every_12_hours: 'Every 12 hours',
			daily: 'Daily',
			weekly: 'Weekly'
		};
		return labels[mode] || mode;
	}

	function getStatusColor(status: string): string {
		switch (status) {
			case 'syncing':
				return 'text-blue-600 dark:text-blue-400';
			case 'error':
				return 'text-red-600 dark:text-red-400';
			default:
				return 'text-green-600 dark:text-green-400';
		}
	}

	function getStatusBgColor(status: string): string {
		switch (status) {
			case 'syncing':
				return 'bg-blue-100 dark:bg-blue-900/30';
			case 'error':
				return 'bg-red-100 dark:bg-red-900/30';
			default:
				return 'bg-green-100 dark:bg-green-900/30';
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

	async function handleSync() {
		syncing = true;
		try {
			const result = await syncDataSource(localStorage.token, dataSource.id);
			if (result.success) {
				toast.success(
					$i18n.t('Sync completed: {{count}} files synced', { count: result.files_synced })
				);
				dispatch('synced', result);
			} else {
				toast.error($i18n.t('Sync failed'));
			}
		} catch (e) {
			toast.error(`Sync failed: ${e}`);
		} finally {
			syncing = false;
		}
	}

	async function handleDelete() {
		if (!confirm($i18n.t('Are you sure you want to delete this data source?'))) {
			return;
		}

		deleting = true;
		try {
			await deleteDataSource(localStorage.token, dataSource.id);
			toast.success($i18n.t('Data source deleted'));
			dispatch('deleted', dataSource.id);
		} catch (e) {
			toast.error(`Failed to delete: ${e}`);
		} finally {
			deleting = false;
		}
	}
</script>

<div
	class="p-4 border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-850 hover:border-gray-300 dark:hover:border-gray-600 transition"
>
	<div class="flex items-start gap-3">
		<!-- Icon -->
		<div
			class="w-10 h-10 flex items-center justify-center bg-gray-100 dark:bg-gray-700 rounded-lg shrink-0"
		>
			<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
				<path d={getSourceTypeIcon(dataSource.source_type)} />
			</svg>
		</div>

		<!-- Content -->
		<div class="flex-1 min-w-0">
			<div class="flex items-center gap-2">
				<h3 class="font-medium truncate">{dataSource.name}</h3>
				<span
					class="px-2 py-0.5 text-xs rounded-full capitalize {getStatusColor(
						dataSource.status
					)} {getStatusBgColor(dataSource.status)}"
				>
					{#if dataSource.status === 'syncing'}
						<span class="flex items-center gap-1">
							<Spinner className="size-3" />
							{$i18n.t('Syncing')}
						</span>
					{:else}
						{dataSource.status}
					{/if}
				</span>
			</div>

			<div class="flex items-center gap-4 mt-1 text-xs text-gray-500 dark:text-gray-400">
				<span class="capitalize">{dataSource.source_type}</span>
				<span>|</span>
				<span>{getSyncModeLabel(dataSource.sync_config?.sync_mode || 'manual')}</span>
			</div>

			<div class="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
				<span>
					{$i18n.t('Last sync')}: {formatTimestamp(dataSource.last_sync_at)}
				</span>
			</div>

			{#if dataSource.status === 'error' && dataSource.last_sync_error}
				<div class="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-600 dark:text-red-400">
					{dataSource.last_sync_error}
				</div>
			{/if}
		</div>

		<!-- Actions -->
		{#if writeAccess}
			<div class="flex items-center gap-1 shrink-0">
				<Tooltip content={$i18n.t('Sync now')}>
					<button
						class="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={syncing || dataSource.status === 'syncing'}
						on:click={handleSync}
					>
						{#if syncing}
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
					</button>
				</Tooltip>

				<Tooltip content={$i18n.t('Delete')}>
					<button
						class="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
						disabled={deleting}
						on:click={handleDelete}
					>
						{#if deleting}
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
					</button>
				</Tooltip>
			</div>
		{/if}
	</div>
</div>
