<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Spinner from '$lib/components/common/Spinner.svelte';
	import DataSourceCard from './DataSourceCard.svelte';
	import CreateDataSourceModal from './CreateDataSourceModal.svelte';
	import { getDataSourcesByKnowledgeId, type DataSource } from '$lib/apis/data_sources';

	export let knowledgeId: string;
	export let writeAccess: boolean = false;

	let loading = true;
	let dataSources: DataSource[] = [];
	let showCreateModal = false;

	onMount(async () => {
		await loadDataSources();
	});

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
		dataSources = dataSources.filter((ds) => ds.id !== event.detail);
		dispatch('changed');
	}

	function handleSynced(event: CustomEvent) {
		loadDataSources();
		dispatch('changed');
	}

	function handleUpdated(event: CustomEvent) {
		const updated = event.detail as DataSource;
		dataSources = dataSources.map((ds) => (ds.id === updated.id ? updated : ds));
		dispatch('changed');
	}
</script>

<CreateDataSourceModal
	bind:show={showCreateModal}
	{knowledgeId}
	on:created={handleCreated}
/>

<div class="space-y-4">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">
			{$i18n.t('External Data Sources')}
		</h3>
		{#if writeAccess}
			<button
				class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition"
				on:click={() => (showCreateModal = true)}
			>
				<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
				</svg>
				{$i18n.t('Add Source')}
			</button>
		{/if}
	</div>

	<!-- Content -->
	{#if loading}
		<div class="flex justify-center py-8">
			<Spinner className="size-5" />
		</div>
	{:else if dataSources.length === 0}
		<div class="text-center py-8 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
			<svg
				class="mx-auto h-10 w-10 text-gray-400"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="1.5"
					d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
				/>
			</svg>
			<p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('No external data sources connected')}
			</p>
			{#if writeAccess}
				<button
					class="mt-3 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
					on:click={() => (showCreateModal = true)}
				>
					{$i18n.t('Connect your first data source')}
				</button>
			{/if}
		</div>
	{:else}
		<div class="space-y-3">
			{#each dataSources as dataSource (dataSource.id)}
				<DataSourceCard
					{dataSource}
					{writeAccess}
					on:synced={handleSynced}
					on:updated={handleUpdated}
					on:deleted={handleDeleted}
				/>
			{/each}
		</div>
	{/if}
</div>
