#!/opt/apps/python/2.7.1/bin/python
import gzip, os, numpy, signal, string, subprocess, sys, time
# signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# TODO Handle changes in schema.
# TODO Sanity check on rollover.
# TODO Check that input values are not wider than allowed.

verbose = True # XXX
prog = os.path.basename(sys.argv[0])
if prog == "":
    prog = "***"

def trace(fmt, *args):
    if verbose:
        msg = fmt % args
        sys.stderr.write(prog + ": " + msg)

def error(fmt, *args):
    msg = fmt % args
    sys.stderr.write(prog + ": " + msg)
    
def fatal(fmt, *args):
    msg = fmt % args
    sys.stderr.write(prog + ": " + msg)
    sys.exit(1)


archive_dir = "/scratch/projects/tacc_stats/archive"
JOB_TIME_PAD = 600
FILE_TIME_MAX = 86400 + 3600 # XXX
SF_SCHEMA_CHAR = '!'
SF_DEVICES_CHAR = '@'
SF_COMMENT_CHAR = '#'
SF_PROPERTY_CHAR = '$'
SF_MARK_CHAR = '%'

job_info_cmd = "/share/home/01114/jhammond/tacc_stats/tacc_job_info" # XXX
def get_job_info(id):
    id = str(id)
    info = {}
    info_proc = subprocess.Popen([job_info_cmd, id], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in info_proc.stdout:
        key, sep, val = line.strip().partition(" ")
        if key != "":
            info[key] = val
    info_id = info.get("id")
    if not info_id:
        # FIXME Prints "cannot get info for job `1971376': tacc_job_info: cannot find accounting data for job 1971376".
        info_err = ""
        for line in info_proc.stderr:
            info_err += line
        error("cannot get info for job `%s': %s\n", id, info_err.strip())
         # return None
    if info_id != id:
        error("%s returned info for wrong job, requested `%s', received `%s'\n", job_info_cmd, id, info_id)
        # return None
    return info


# amd64
# define PERF_EVENT(event_select, unit_mask) \
#  ( (event_select & 0xFF) \
#  | (unit_mask << 8) \
#  | (1UL << 16) /* Count in user mode (CPL == 0). */ \
#  | (1UL << 17) /* Count in OS mode (CPL > 0). */ \
#  | (1UL << 22) /* Enable. */ \
#  | ((event_select & 0xF00) << 24) \
#  )

def amd64_perf_event(event_select, unit_mask):
    return (event_select & 0xFF) | (unit_mask << 8) | (1L << 16) | (1L << 17) | (1L << 22) | ((event_select & 0xF00) << 24)

#define DRAMaccesses   PERF_EVENT(0xE0, 0x07) /* DCT0 only */
#define HTlink0Use     PERF_EVENT(0xF6, 0x37) /* Counts all except NOPs */
#define HTlink1Use     PERF_EVENT(0xF7, 0x37) /* Counts all except NOPs */
#define HTlink2Use     PERF_EVENT(0xF8, 0x37) /* Counts all except NOPs */
#define UserCycles    (PERF_EVENT(0x76, 0x00) & ~(1UL << 17))
#define DCacheSysFills PERF_EVENT(0x42, 0x01) /* Counts DCache fills from beyond the L2 cache. */
#define SSEFLOPS       PERF_EVENT(0x03, 0x7F) /* Counts single & double, add, multiply, divide & sqrt FLOPs. */

dram_accesses = amd64_perf_event(0xE0, 0x07)
ht_link_0_use = amd64_perf_event(0xF6, 0x37)
ht_link_1_use = amd64_perf_event(0xF7, 0x37)
ht_link_2_use = amd64_perf_event(0xF8, 0x37)
user_cycles = amd64_perf_event(0x76, 0x00) & ~(1L << 17)
dcache_sys_fills = amd64_perf_event(0x42, 0x01)
sse_flops = amd64_perf_event(0x03, 0x7F)

amd64_core_ctls = {
    user_cycles: 0,
    dcache_sys_fills: 1,
    sse_flops: 2,
    }

amd64_sock_ctls = {
    dram_accesses: 0,
    ht_link_0_use: 1,
    ht_link_1_use: 2,
    ht_link_2_use: 3,
    }

amd64_mults = {
    user_cycles: 1,
    dcache_sys_fills: 64, # DCSFs are 64B.
    sse_flops: 1,
    dram_accesses: 64, # DRAM accesses are 64B.
    ht_link_0_use: 4, # Each HT event counter increment represents 4B.
    ht_link_1_use: 4,
    ht_link_2_use: 4,
    }

class Job(object):
    def __init__(self, id, info=None):
        self.id = str(id)
        self.begin = 0
        self.end = 0
        self.types = {}
        self.hosts = {}
        self.bad_hosts = {}
        self.info = info
        if not self.info:
            self.info = get_job_info(self.id)
        if not self.info:
            return
        self.id = self.info["id"]
        self.begin = long(self.info["start_time"])
        self.end = long(self.info["end_time"])
        host_list = self.info["hosts"].split()
        if len(host_list) == 0:
            error("empty host list for job `%s'\n", id)
        for host in host_list:
            entry = HostEntry(self, host)
            if len(entry.times) < 2: # BLECH.
                self.bad_hosts[host] = entry
                continue
            self.hosts[host] = entry
            for type_name, type_data in entry.types.iteritems():
                for dev in type_data.devs():
                    self.types[type_name].devs.add(dev)
        # TODO Warn about bad hosts.
        if 'amd64_pmc' in self.types:
            self.process_amd64()
    def process_amd64(self):
        self.get_schema('amd64_core', 'USER,E DCSF,E SSE_FLOPS,E')
        self.types['amd64_core'].devs = set(map(str, range(0, 16))) # BLECH.
        self.get_schema('amd64_sock', 'DRAM,E HT0,E HT1,E HT2,E')
        self.types['amd64_sock'].devs = set(map(str, range(0, 4))) # BLECH.
        for host_entry in self.hosts.itervalues():
            orig_data = host_entry.types['amd64_pmc']
            core_data = host_entry.add_type('amd64_core', 'USER,E DCSF,E SSE_FLOPS,E')
            sock_data = host_entry.add_type('amd64_sock', 'DRAM,E HT0,E HT1,E HT2,E')
            # Assume no stray times.
            times = orig_data.times['0']
            nr_rows = len(times)
            for sock_nr in range(0, 4):
                sock_dev = str(sock_nr)
                sock_data.times[sock_dev] = numpy.array(times, numpy.uint64)
                sock_stats = sock_data.stats[sock_dev] = numpy.zeros((nr_rows, 4), numpy.uint64)
                for core_nr in range(4 * sock_nr, 4 * (sock_nr + 1)):
                    core_dev = str(core_nr)
                    orig_stats = orig_data.stats[core_dev]
                    core_data.times[core_dev] = numpy.array(times, numpy.uint64)
                    core_stats = core_data.stats[core_dev] = numpy.zeros((nr_rows, 3), numpy.uint64)
                    # Assume schema is still CTL{0..3} CTR{0..3}.
                    for row in range(0, nr_rows):
                        for ctl_nr in range(0, 4):
                            ctl = orig_stats[row][ctl_nr]
                            val = orig_stats[row][ctl_nr + 4]
                            if ctl in amd64_sock_ctls:
                                col = amd64_sock_ctls[ctl]
                                sock_stats[row][col] += val * amd64_mults[ctl]
                            elif ctl in amd64_core_ctls:
                                col = amd64_core_ctls[ctl]
                                core_stats[row][col] += val * amd64_mults[ctl]
                            else:
                                # TODO Improve error detection.
                                error("unknown PMC control value %d\n", ctl)
                                del self.types['amd64_core']
                                del self.types['amd64_sock']
                                return
    def get_schema(self, type_name, desc=None):
        if desc:
            # TODO Warn about schema changes.
            data = self.types.get(type_name)
            if not data:
                data = JobTypeData(type_name)
                self.types[type_name] = data
            schema = data.schemas.get(desc)
            if not schema:
                schema = Schema(type_name, desc)
                data.schemas[desc] = schema
            return schema
        else:
            type_data = self.types.get(type_name)
            if not type_data:
                return None
            if len(type_data.schemas) != 1:
                error("multiple schemas for type `%s'\n", type_name)
                return None
            for schema in type_data.schemas.itervalues():
                return schema


class JobTypeData(object):
    def __init__(self, name):
        self.name = name
        self.schemas = {}
        self.devs = set()


def get_stats_paths(job, host_name):
    files = []
    host_dir = os.path.join(archive_dir, host_name)
    trace("host_name `%s', host_dir `%s'\n", host_name, host_dir)
    try:
        for dent in os.listdir(host_dir):
            base, dot, ext = dent.partition(".")
            if not base.isdigit():
                continue
            # TODO Pad end.
            # Prune to files that might overlap with job.
            file_begin = long(base)
            file_end_max = file_begin + FILE_TIME_MAX
            if max(job.begin - JOB_TIME_PAD, file_begin) <= min(job.end + JOB_TIME_PAD, file_end_max):
                files.append((file_begin, os.path.join(host_dir, dent)))
        files.sort(key=lambda tup: tup[0])
        # trace("host_name `%s', files `%s'\n", host_name, files)
        return [tup[1] for tup in files]
    except:
        return []


class HostEntry(object):
    def __init__(self, job, name):
        self.job = job
        self.name = name
        self.types = {}
        self.times = []
        self.marks = {}
        end_mark = "end %s" % job.id
        self.stats_file_paths = get_stats_paths(job, self.name)
        if len(self.stats_file_paths) == 0:
            error("host `%s' has no stats files overlapping job `%s'\n", self.name, job.id)
        for path in self.stats_file_paths:
            self.read_stats_file(gzip.open(path))
            if end_mark in self.marks:
                break
        # TODO Check for begin, end mark.
        for type_data in self.types.itervalues():
            type_data.process_stats()
    def read_stats_file(self, file):
        job_id = self.job.id
        rec_time = 0
        rec_job_id = ""
        for line in file:
            c = line[0]
            if c.isalpha():
                if rec_job_id == job_id:
                    type_name, sep, rest = line.partition(' ')
                    dev, sep, val_str = rest.partition(' ')
                    self.add_stats(rec_time, type_name, dev, val_str)
                elif len(self.times) != 0:
                    return # We're done.
            elif c.isdigit():
                str_time, rec_job_id = line.split()
                if rec_job_id == job_id:
                    rec_time = long(str_time)
                    self.times.append(rec_time)
            elif c.isspace():
                pass
            elif c == SF_SCHEMA_CHAR:
                type_name, sep, schema_desc = line[1:].partition(" ")
                self.add_type(type_name, schema_desc)
            elif c == SF_DEVICES_CHAR:
                pass # TODO
            elif c == SF_COMMENT_CHAR:
                pass
            elif c == SF_PROPERTY_CHAR:
                pass # TODO
            elif c == SF_MARK_CHAR:
                if rec_job_id == job_id:
                    self.add_mark(rec_time, line[1:].strip())
            else:
                error("%s: unrecognized directive `%s'\n", file.name, line.strip())
    def add_type(self, type_name, schema_desc):
        type_data = self.types.get(type_name)
        if not type_data:
            schema = self.job.get_schema(type_name, desc=schema_desc)
            type_data = HostTypeData(type_name, schema)
            self.types[type_name] = type_data
        if type_data.schema.desc != schema_desc: # BLECH.
            error("schema changed for type `%s', host `%s'\n", type_name, self.name)
        return type_data
    def add_stats(self, rec_time, type_name, dev, val_str):
        type_data = self.types.get(type_name)
        if not type_data:
            error("no data for type `%s', host `%s', dev `%s'\n", type_name, self.name, dev)
            return
        type_data.add_stats(rec_time, dev, val_str)
    def add_mark(self, rec_time, mark):
        self.marks.setdefault(mark, []).append(rec_time)


class HostTypeData(object):
    def __init__(self, type_name, schema):
        self.name = type_name
        self.schema = schema
        self.times = {}
        self.stats = {}
    def devs(self):
        return self.times.keys()
    def add_stats(self, time, dev, val_str):
        nr_cols = len(self.schema.entries)
        vals = numpy.zeros(nr_cols, numpy.uint64)
        for i, s in enumerate(val_str.split()):
            if i < nr_cols:
                vals[i] = s
            else:
                error("type `%s', dev `%s': too many values\n", self.name, dev)
        self.times.setdefault(dev, []).append(time)
        self.stats.setdefault(dev, []).append(vals)
    def process_stats(self):
        for dev in self.times.keys():
            self.times[dev] = numpy.array(self.times[dev], numpy.uint64)
            nr_rows = len(self.times[dev])
            nr_cols = len(self.schema.entries)
            old_stats = self.stats[dev]
            new_stats = self.stats[dev] = numpy.zeros((nr_rows, nr_cols), numpy.uint64)
            base_vals = numpy.array(old_stats[0], numpy.uint64)
            prev_vals = old_stats[0]
            for row in range(0, nr_rows):
                for new_col, entry in enumerate(self.schema.entries):
                    old_col = entry.index
                    val = old_stats[row][old_col]
                    if entry.event:
                        prev_val = prev_vals[old_col]
                        if val < prev_val:
                            width = entry.width or 64 # XXX
                            if prev_val - val < 0.25 * (2.0 ** width): #XXX
                                trace("spurious rollover on type `%s', dev `%s', counter `%s', val %d, prev %d\n",
                                      self.name, dev, entry.key, val, prev_val)
                                val = prev_val
                            else:
                                if self.name != "amd64_pmc": # XXX
                                    error("rollover on type `%s', dev `%s', counter `%s', val %d, prev %d\n",
                                          self.name, dev, entry.key, val, prev_val)
                                base_vals[old_col] -= numpy.uint64(1L << width)
                        val -= base_vals[old_col]
                    if entry.mult:
                        val *= entry.mult
                    new_stats[row][new_col] = val
                prev_vals = old_stats[row]


class Schema(object):
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.entries = []
        self.keys = {}
        for index, entry_desc in enumerate(desc.split()):
            entry = SchemaEntry(index, entry_desc)
            self.keys[entry.key] = entry
            self.entries.append(entry)


class SchemaEntry(object):
    def __init__(self, index, desc):
        opt_lis = desc.split(',')
        self.key = opt_lis[0]
        self.index = index
        self.control = False
        self.event = False
        self.width = None
        self.mult = None
        self.unit = None
        # TODO Add gauge.
        for opt in opt_lis[1:]:
            if len(opt) == 0:
                continue
            elif opt[0] == 'C':
                self.control = True
            elif opt[0] == 'E':
                self.event = True
            elif opt[0:2] == 'W=':
                self.width = int(opt[2:])
            elif opt[0:2] == 'U=':
                i = 2
                while i < len(opt) and opt[i].isdigit():
                    i += 1
                if i > 2:
                    self.mult = numpy.uint64((opt[2:i]))
                if i < len(opt):
                    self.unit = opt[i:]
                if self.unit == "KB":
                    self.mult = numpy.uint64(1024)
                    self.unit = "B"
            else:
                error("unrecognized option `%s' in schema entry spec `%s'\n", opt, desc)

