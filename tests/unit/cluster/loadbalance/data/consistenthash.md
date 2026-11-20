# Consistent-hash assignments

Migrated unchanged from `tests/test_loadbalance.py` at the `baseline` commit.
That test records Dubbo for Go's
`cluster/loadbalance/consistenthashing/selector.go` as the generator.
The baseline does not record a peer version or generation command; neither
has been reconstructed here. These are recorded regression assignments,
not evidence of a newly executed Go or Java interoperability run.

Provider addresses: `10.0.0.1:20880`, `10.0.0.2:20880`, `10.0.0.3:20880`.
Arguments consisting only of digits are integers; the other arguments are
strings. The empty key is the empty string. Queries select the default
160 ring points per provider or eight points per provider.
