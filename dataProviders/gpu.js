import { GpuUsage } from './gpuUsage.js'

export const MAX_CPU_UTILIZATION = 1.0

// Weight of the newest sample in the moving average. NVIDIA reports the
// busy fraction of a very short window, so single samples jump around
// (e.g. 5% then 70% one poll later); averaging gives a steady reading.
const SMOOTHING = 0.35

// Yields the busiest GPU's utilization in [0, 1], smoothed with an
// exponential moving average. Sleeping GPUs are never woken.
export default async function* () {
	const gpu = new GpuUsage()
	await gpu.total() // prime residency baselines
	let avg = null
	while (true) {
		const v = await gpu.total()
		avg = avg === null ? v : avg + SMOOTHING * (v - avg)
		yield avg
	}
}
