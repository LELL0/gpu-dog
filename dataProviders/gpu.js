import { GpuUsage } from './gpuUsage.js'

export const MAX_CPU_UTILIZATION = 1.0

// Weight of the newest sample in the moving average. NVIDIA reports the
// busy fraction of a very short window, so single samples jump around
// (e.g. 5% then 70% one poll later); averaging gives a steady reading.
const SMOOTHING = 0.35

// Yields { usage, vendor }: the busiest GPU's utilization in [0, 1],
// smoothed with an exponential moving average, and that GPU's PCI vendor id
// (used to color the character). Sleeping GPUs are never woken.
export default async function* () {
	const gpu = new GpuUsage()
	await gpu.total() // prime residency baselines
	let avg = null
	while (true) {
		const { value, vendor } = await gpu.busiest()
		avg = avg === null ? value : avg + SMOOTHING * (value - avg)
		yield { usage: avg, vendor }
	}
}
