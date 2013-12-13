#!/usr/bin/env python
"""
Test of using the LibVirt Python bindings to gather
information about libvirt (qemu/KVM) guests.

test on opskvmtie13
"""

import libvirt
import sys

if len(sys.argv) > 1:
    hostname = sys.argv[1]
else:
    print("USAGE: test_libvirt.py <hostname>")
    sys.exit(1)

uri = "qemu+ssh://%s/system" % hostname

print("Using hostname: %s (URI: %s)" % (hostname, uri))

try:
    conn = libvirt.openReadOnly(uri)
except libvirt.libvirtError as e:
    print("ERROR connecting to %s: %s" % (uri, e.message))
    sys.exit(1)

# some code examples imply that older versions
# returned None instead of raising an exception
if conn is None:
    print("ERROR connecting to %s: %s" % (uri, e.message))
    sys.exit(1)

# bitwise or of all possible flags to virConnectListAllDomains
ALL_OPTS = 16383

domains = conn.listAllDomains(ALL_OPTS)
print domains

states = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED: 'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
    libvirt.VIR_DOMAIN_PMSUSPENDED: 'suspended by guest power mgmt',
}

def bool(a):
    if a == 0:
        return False
    return True

for d in domains:
    print d
    for m in ['name', 'ID', 'OSType', 'UUIDString', 'isActive', 'isPersistent', 'isUpdated']:
        print("%s: %s" % (m, getattr(d, m)()))
    [state, maxmem, mem, ncpu, cputime] = d.info()
    print states.get(state, state)
    break

"""
domain object methods:
abortJob
attachDevice
attachDeviceFlags
autostart
blkioParameters
blockCommit
blockInfo
blockIoTune
blockJobAbort
blockJobInfo
blockJobSetSpeed
blockPeek
blockPull
blockRebase
blockResize
blockStats
blockStatsFlags
connect
controlInfo
coreDump
create
createWithFlags
destroy
destroyFlags
detachDevice
detachDeviceFlags
diskErrors
emulatorPinInfo
getCPUStats
hasCurrentSnapshot
hasManagedSaveImage
hostname
info
injectNMI
interfaceParameters
interfaceStats
isActive
isPersistent
isUpdated
jobInfo
listAllSnapshots
managedSave
managedSaveRemove
maxMemory
maxVcpus
memoryParameters
memoryPeek
memoryStats
metadata
migrate
migrate2
migrateGetMaxSpeed
migrateSetMaxDowntime
migrateSetMaxSpeed
migrateToURI
migrateToURI2
name
numaParameters
openConsole
openGraphics
pMSuspendForDuration
pMWakeup
pinEmulator
pinVcpu
pinVcpuFlags
reboot
reset
resume
revertToSnapshot
save
saveFlags
schedulerParameters
schedulerParametersFlags
schedulerType
screenshot
sendKey
setAutostart
setBlkioParameters
setBlockIoTune
setInterfaceParameters
setMaxMemory
setMemory
setMemoryFlags
setMemoryParameters
setMetadata
setNumaParameters
setSchedulerParameters
setSchedulerParametersFlags
setVcpus
setVcpusFlags
shutdown
shutdownFlags
snapshotCreateXML
snapshotCurrent
snapshotListNames
snapshotLookupByName
snapshotNum
state
suspend
undefine
undefineFlags
updateDeviceFlags
vcpuPinInfo
vcpus
vcpusFlags





conn object methods:
baselineCPU
changeBegin
changeCommit
changeRollback
close
compareCPU
createLinux
createXML
defineXML
dispatchDomainEventBlockPullCallback
domainEventDeregister
domainEventDeregisterAny
domainEventRegister
domainEventRegisterAny
domainXMLFromNative
domainXMLToNative
findStoragePoolSources
getCPUStats
getCapabilities
getCellsFreeMemory
getFreeMemory
getHostname
getInfo
getLibVersion
getMaxVcpus
getMemoryParameters
getMemoryStats
getSysinfo
getType
getURI
getVersion
interfaceDefineXML
interfaceLookupByMACString
interfaceLookupByName
isAlive
isEncrypted
isSecure
listAllDevices
listAllDomains
listAllInterfaces
listAllNWFilters
listAllNetworks
listAllSecrets
listAllStoragePools
listDefinedDomains
listDefinedInterfaces
listDefinedNetworks
listDefinedStoragePools
listDevices
listDomainsID
listInterfaces
listNWFilters
listNetworks
listSecrets
listStoragePools
lookupByID
lookupByName
lookupByUUID
lookupByUUIDString
migrate
migrate2
networkCreateXML
networkDefineXML
networkLookupByName
networkLookupByUUID
networkLookupByUUIDString
newStream
nodeDeviceCreateXML
nodeDeviceLookupByName
numOfDefinedDomains
numOfDefinedInterfaces
numOfDefinedNetworks
numOfDefinedStoragePools
numOfDevices
numOfDomains
numOfInterfaces
numOfNWFilters
numOfNetworks
numOfSecrets
numOfStoragePools
nwfilterDefineXML
nwfilterLookupByName
nwfilterLookupByUUID
nwfilterLookupByUUIDString
registerCloseCallback
restore
restoreFlags
saveImageDefineXML
saveImageGetXMLDesc
secretDefineXML
secretLookupByUUID
secretLookupByUUIDString
secretLookupByUsage
setKeepAlive
setMemoryParameters
storagePoolCreateXML
storagePoolDefineXML
storagePoolLookupByName
storagePoolLookupByUUID
storagePoolLookupByUUIDString
storageVolLookupByKey
storageVolLookupByPath
suspendForDuration
unregisterCloseCallback
virConnGetLastError
virConnResetLastError
"""

