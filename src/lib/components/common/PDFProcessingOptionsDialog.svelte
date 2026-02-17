<script lang="ts">
	import { onMount, getContext, createEventDispatcher, onDestroy, tick } from 'svelte';
	import * as FocusTrap from 'focus-trap';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import { fade } from 'svelte/transition';
	import { flyAndScale } from '$lib/utils/transitions';

	export let show = false;
	export let fileName = '';
	export let pageCount = 0;

	let modalElement = null;
	let mounted = false;
	let focusTrap: FocusTrap.FocusTrap | null = null;

	const handleChoice = (choice: 'normal' | 'advanced') => {
		show = false;
		dispatch('select', { choice });
	};

	const handleCancel = () => {
		show = false;
		dispatch('cancel');
	};

	const handleKeyDown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') {
			handleCancel();
		}
	};

	onMount(() => {
		mounted = true;
	});

	$: if (mounted) {
		if (show && modalElement) {
			document.body.appendChild(modalElement);
			focusTrap = FocusTrap.createFocusTrap(modalElement);
			focusTrap.activate();

			window.addEventListener('keydown', handleKeyDown);
			document.body.style.overflow = 'hidden';
		} else if (modalElement) {
			if (focusTrap) {
				focusTrap.deactivate();
			}

			window.removeEventListener('keydown', handleKeyDown);
			if (document.body.contains(modalElement)) {
				document.body.removeChild(modalElement);
			}

			document.body.style.overflow = 'unset';
		}
	}

	onDestroy(() => {
		show = false;
		if (focusTrap) {
			focusTrap.deactivate();
		}
		if (modalElement && document.body.contains(modalElement)) {
			document.body.removeChild(modalElement);
		}
	});
</script>

{#if show}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		bind:this={modalElement}
		class="fixed top-0 right-0 left-0 bottom-0 bg-black/60 w-full h-screen max-h-[100dvh] flex justify-center z-99999999 overflow-hidden overscroll-contain"
		in:fade={{ duration: 10 }}
		on:mousedown={handleCancel}
	>
		<div
			class="m-auto max-w-full w-[32rem] mx-2 bg-white/95 dark:bg-gray-950/95 backdrop-blur-sm rounded-4xl max-h-[100dvh] shadow-3xl border border-white dark:border-gray-900"
			in:flyAndScale
			on:mousedown={(e) => {
				e.stopPropagation();
			}}
		>
			<div class="px-[1.75rem] py-6 flex flex-col">
				<!-- Title -->
				<div class="text-lg font-medium dark:text-gray-200 mb-2.5">
					{$i18n.t('Large PDF Detected')}
				</div>

				<!-- File Info -->
				<div class="text-sm text-gray-600 dark:text-gray-400 mb-4">
					<div class="font-medium">{fileName}</div>
					<div class="text-xs mt-1">
						{pageCount}
						{pageCount === 1 ? $i18n.t('page') : $i18n.t('pages')}
					</div>
				</div>

				<!-- Message -->
				<div class="text-sm text-gray-500 dark:text-gray-400 mb-5">
					{$i18n.t('Choose how to process this PDF file:')}
				</div>

				<!-- Options -->
				<div class="flex flex-col gap-3 mb-4">
					<!-- Fast Processing Button -->
					<button
						class="text-left bg-gray-100 hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800 rounded-xl p-4 transition"
						on:click={() => handleChoice('normal')}
						type="button"
					>
						<div class="font-medium text-gray-900 dark:text-gray-100 mb-1">
							{$i18n.t('Fast Processing')}
						</div>
						<div class="text-xs text-gray-600 dark:text-gray-400">
							{$i18n.t('Standard text extraction. Best for text-only documents.')}
						</div>
					</button>

					<!-- Advanced Processing Button -->
					<button
						class="text-left bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/50 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800 rounded-xl p-4 transition"
						on:click={() => handleChoice('advanced')}
						type="button"
					>
						<div class="font-medium text-gray-900 dark:text-gray-100 mb-1">
							{$i18n.t('Advanced Processing (Slow)')}
						</div>
						<div class="text-xs text-gray-600 dark:text-gray-400">
							{$i18n.t('Enhanced extraction with images and complex layouts. May take longer.')}
						</div>
					</button>
				</div>

				<!-- Cancel Button -->
				<button
					class="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 py-2"
					on:click={handleCancel}
					type="button"
				>
					{$i18n.t('Cancel')}
				</button>
			</div>
		</div>
	</div>
{/if}
