// Machine "ear": runs Apple's built-in sound classifier (SoundAnalysis, version1, 303 labels)
// over WAV files and prints the strongest labels. QC helper only -- not needed to build the audio.
// Build: swiftc -O ear.swift -o ear     Usage: ear [-n TOP] [-w WINDOW_SECONDS] [-v] file.wav ...
import Foundation
import SoundAnalysis
import CoreMedia

final class Collector: NSObject, SNResultsObserving {
    var windows: [(Double, [(String, Double)])] = []
    var failed: Error?
    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let r = result as? SNClassificationResult else { return }
        let pairs = r.classifications.map { ($0.identifier, Double($0.confidence)) }
        windows.append((r.timeRange.start.seconds, pairs))
    }
    func request(_ request: SNRequest, didFailWithError error: Error) { failed = error }
    func requestDidComplete(_ request: SNRequest) {}
}

var top = 6
var window: Double? = nil
var verbose = false
var files: [String] = []
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    if a == "-n", let v = it.next(), let n = Int(v) { top = n }
    else if a == "-w", let v = it.next(), let w = Double(v) { window = w }
    else if a == "-v" { verbose = true }
    else { files.append(a) }
}

for path in files {
    let url = URL(fileURLWithPath: path)
    do {
        let analyzer = try SNAudioFileAnalyzer(url: url)
        let req = try SNClassifySoundRequest(classifierIdentifier: .version1)
        if let w = window { req.windowDuration = CMTime(seconds: w, preferredTimescale: 48000) }
        req.overlapFactor = 0.5
        let col = Collector()
        try analyzer.add(req, withObserver: col)
        analyzer.analyze()
        let name = url.lastPathComponent
        if let e = col.failed { print("\(name)\tERROR \(e)"); continue }
        if col.windows.isEmpty { print("\(name)\t(no windows)"); continue }
        var mean: [String: Double] = [:]
        var peak: [String: Double] = [:]
        for (_, pairs) in col.windows {
            for (k, v) in pairs {
                mean[k, default: 0] += v / Double(col.windows.count)
                peak[k] = max(peak[k] ?? 0, v)
            }
        }
        let ranked = mean.sorted { $0.value > $1.value }.prefix(top)
        let s = ranked.map { String(format: "%@ %.2f(%.2f)", $0.key, $0.value, peak[$0.key] ?? 0) }.joined(separator: ", ")
        print("\(name)\t[\(col.windows.count)w] \(s)")
        if verbose {
            for (t, pairs) in col.windows {
                let r = pairs.sorted { $0.1 > $1.1 }.prefix(4).map { String(format: "%@ %.2f", $0.0, $0.1) }.joined(separator: ", ")
                print(String(format: "    t=%.2f  %@", t, r))
            }
        }
    } catch {
        print("\(url.lastPathComponent)\tERROR \(error)")
    }
}
