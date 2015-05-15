#!/usr/bin/python

from __future__ import print_function
from parse import parse
import sys
import os
try:
    import cPickle as pickle
except:
    import pickle
import uuid
import shutil
import numpy as np
from . import cfg

from .docker_tools import docker_images_available, is_running_in_docker

class MissingRequiredParameterError(Exception):

    """Required parameter is not provided in feature function call."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


class MissingRequiredReturnKeyError(Exception):

    """Required return value is not provided in feature definition."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


class myFeature(object):

    """Decorator for custom-defined time series feature(s) function.

    Applies function wrapper that ensures required parameters and
    return values are present before executing, raising an exception if
    not.

    Attributes
    ----------
    requires : list
        List of names of features required for decorated function to
        execute.
    provides : list
        List of names of features generated by decorated function.

    """

    def __init__(self, requires, provides):
        """Instantiates object, sets args as attributes.

        Parameters
        ----------
        requires : list
            List of variable names required by the function.
        provides : list
            List of the key names of the returned dictionary - the
            features calculated by a particular function.

        """
        self.requires = requires
        self.provides = provides

    def __call__(self, f):
        """Wrap decorated function.

        Wrap decorated function with a check to ensure that required
        parameters (specified in decorator expression) are provided
        upon function call (raises MissingRequiredParameterError if
        not) and that all features reportedly returned (specified in
        decorator expression) are in fact returned (raises
        MissingRequiredReturnKeyError if not).

        Returns
        -------
        function
            The wrapped function.

        """
        def wrapped_f(*args, **kwargs):
            for required_arg in self.requires:
                if required_arg not in args and required_arg not in kwargs:
                    raise MissingRequiredParameterError(
                        "Required arg %s not provided in function call." %
                        required_arg)
            result_dict = f(*args, **kwargs)
            for provided in self.provides:
                if provided not in result_dict:
                    raise MissingRequiredReturnKeyError(
                        "Key %s not present in function return value." %
                        provided)
            return result_dict
        return wrapped_f


class DummyFile(object):

    """Used as a file object to temporarily redirect/suppress output."""

    def write(self, x):
        pass



def parse_csv_file(fname, sep=',', skip_lines=0):
    """Parse 2- or 3-column CSV file and return a list of its columns.

    Parameters
    ----------
    fname : str
        Absolute path to the CSV file.
    sep : str, optional
        Delimiter in TS data file, defaults to ",".
    skip_lines : int, optional
        Number of leading lines to skip in file, defaults to 0.

    Returns
    -------
    list of list
        Two- or three-element list of lists of each of the columns. If
        `fname` is not a 2- or 3-column CSV file, returns list of three
        empty lists.

    """
    with open(fname, "r") as f:
        ts_data = np.loadtxt(f, delimiter=",", skiprows=skip_lines)
    ts_data = ts_data[:, :3].tolist()  # Only using T, M, E; convert to list
    for row in ts_data:
        if len(row) < 2:
            raise custom_exceptions.DataFormatError(
                "Incomplete or improperly formatted time "
                "series data file provided.")
    tme = list(map(list, zip(*ts_data)))  # Need t, m, and e in separate lists
    if len(tme) == 2:
        tme.append([])  # Add empty err col
    return tme


def parse_for_req_prov_params(script_fpath):
    """
    """
    with open(script_fpath, "r") as f:
        all_lines = f.readlines()
    fnames_req_prov_dict = {}
    all_required_params = []
    all_provided_params = []
    for i in range(len(all_lines) - 1):
        if "@myFeature" in all_lines[i] and "def " in all_lines[i + 1]:
            reqs_provs_1 = parse(
                "@myFeature(requires={requires}, provides={provides})",
                all_lines[i].strip())
            func_name = parse(
                "def {funcname}({args}):", all_lines[i + 1].strip())
            fnames_req_prov_dict[func_name.named['funcname']] = {
                "requires": eval(reqs_provs_1.named["requires"]),
                "provides": eval(reqs_provs_1.named["provides"])}
            all_required_params = list(set(
                all_required_params +
                list(set(eval(reqs_provs_1.named["requires"])))))
            all_provided_params = list(set(
                all_provided_params +
                list(set(eval(reqs_provs_1.named["provides"])))))
    return (fnames_req_prov_dict, all_required_params, all_provided_params)


def listify_feats_known_dict(features_already_known):
    """
    """
    if isinstance(features_already_known, dict):
        return [features_already_known]
    elif isinstance(features_already_known, list):
        return features_already_known
    else:
        raise ValueError("custom_feature_tools.py - features_already_known"
                         " is of an invalid type (%s)." %
                         str(type(features_already_known)))


def call_custom_functions(features_already_known_list, all_required_params,
                          all_provided_params, fnames_req_prov_dict):
    """
    """
    # import the custom feature defs
    try:
        from .custom_feature_scripts import custom_feature_defs
    except ImportError:
        try:
            import custom_feature_defs
        except ImportError:
            raise

    # temporarily redirect stdout:
    save_stdout = sys.stdout
    sys.stdout = DummyFile()

    all_extracted_features_list = []
    for features_already_known in features_already_known_list:
        all_required_params_copy = [x for x in all_required_params
                                    if x not in features_already_known]
        for reqd_param in all_required_params_copy:
            if reqd_param not in all_provided_params:
                raise Exception((
                    "Not all of the required parameters are provided by the "
                    "functions in this script (required parameter '%s').") %
                    str(reqd_param))
        funcs_round_1 = []
        func_queue = []
        funcnames = list(fnames_req_prov_dict.keys())
        i = 0
        func_rounds = {}
        all_extracted_features = {}
        while len(funcnames) > 0:
            func_rounds[str(i)] = []
            for funcname in funcnames:
                reqs_provs_dict = fnames_req_prov_dict[funcname]
                reqs = reqs_provs_dict['requires']
                provs = reqs_provs_dict['provides']
                if len(set(all_required_params_copy) & set(reqs)) > 0:
                    func_queue.append(funcname)
                else:
                    func_rounds[str(i)].append(funcname)
                    all_required_params_copy = [x for x in all_required_params_copy
                                                if x not in provs]
                    arguments = {}
                    for req in reqs:
                        if req in features_already_known:
                            arguments[req] = features_already_known[req]
                        elif req in all_extracted_features:
                            arguments[req] = all_extracted_features[req]
                    func_result = getattr(
                        custom_feature_defs, funcname)(**arguments)
                    all_extracted_features = dict(
                        list(all_extracted_features.items()) +
                        list(func_result.items()))
                    funcnames.remove(funcname)
            i += 1
        all_extracted_features_list.append(all_extracted_features)
    # revert to original stdout
    sys.stdout = save_stdout
    return all_extracted_features_list


def execute_functions_in_order(
        script_fpath,
        features_already_known={
            "t": [1, 2, 3], "m": [1, 23, 2], "e": [0.2, 0.3, 0.2],
            "coords": [22, 33]},
        multiple_sources=False):
    """Generate custom features defined in script_fpath.

    Parses the script (which must have function definitions with
    decorators specifying the required parameters and those which are
    provided by each function) and executes the functions defined in
    that script such that all functions whose outputs are required
    as inputs of other functions are called first, if possible,
    otherwise raises an Exception.

    Parameters
    ----------
    script_fpath : str
        Path to custom feature definitions script.
    features_already_known : dict
        Dictionary providing all time-series data (time ("t"), magnitude
        ("m"), error ("e") as keys) and any meta-features.
        Example:
            {"t": [1, 2, 3], "m": [10.32, 11.41, 11.06],
             "e": [0.2015,0.3134,0.2953], "coords": [22.55,33.01]}

    Returns
    -------
    dict
        Dictionary of all extracted features (key-value pairs are
        feature name and feature value respectively).

    """
    # For when run inside Docker container:
    try:
        sys, os
    except NameError:
        import sys
        import os

    fnames_req_prov_dict, all_required_params, all_provided_params = \
        parse_for_req_prov_params(script_fpath)
    features_already_known_list = listify_feats_known_dict(
        features_already_known)

    all_extracted_features_list = call_custom_functions(
        features_already_known_list, all_required_params, all_required_params,
        fnames_req_prov_dict)

    return all_extracted_features_list



def parse_tsdata_to_lists(ts_data):
    """
    """
    tme = []
    if isinstance(ts_data, list):
        if len(ts_data) > 0:
            if isinstance(ts_data[0], (list, tuple)):
                # ts_data already in desired format
                tme = ts_data
            elif isinstance(ts_data[0], (str, type(u''))) and \
                    "," in ts_data[0]:
                for el in ts_data:
                    if str(el) not in ["\n", ""]:
                        tme.append(el.split(","))
        else:
            raise ValueError("ts_data is an empty list")
    elif isinstance(ts_data, (str, unicode)):
        all_lines = str(ts_data).strip().split("\n")
        for i in range(len(all_lines)):
            if all_lines[i].strip() == "":
                continue
            else:
                tme.append([x.strip()
                            for x in all_lines[i].strip().split(",")])
    else:
        try:
            all_lines = str(ts_data).strip().split("\n")
            for i in range(len(all_lines)):
                if all_lines[i].strip() == "":
                    continue
                else:
                    tme.append([x.strip()
                                for x in all_lines[i].strip().split(",")])
        except:
            pass
    return tme


def parse_tsdata_from_file(ts_datafile_path):
    """
    """
    with open(ts_datafile_path, "r") as f:
        ts_data = np.loadtxt(f, delimiter=",")
    ts_data = ts_data[:, :3].tolist()  # Only using T, M, E; convert to list
    for row in ts_data:
        if len(row) < 2:
            raise custom_exceptions.DataFormatError(
                "Incomplete or improperly formatted time "
                "series data file provided.")
    return ts_data


def add_tsdata_to_feats_known_dict(features_already_known_list,
                                   ts_datafile_paths, ts_data_list):
    """
    """
    if ts_datafile_paths is None:
        ts_datafile_paths = [None] * len(features_already_known_list)
    elif ts_data_list is None:
        ts_data_list = [None] * len(features_already_known_list)
    for i in range(len(features_already_known_list)):
        if "t" not in features_already_known_list[i] or \
           "m" not in features_already_known_list[i]:
            # Get TS data and put into features_already_known_list
            if ts_datafile_paths[i] is None and ts_data_list[i] is None:
                raise ValueError("No time series data provided! ts_datafile_paths "
                                 "is None and ts_data_list is None  !!")
            if ts_datafile_paths[i] is not None:  # path to ts data file
                # parse ts data and put t,m(,e) into features_already_known
                tme = parse_tsdata_from_file(ts_datafile_paths[i])
            else:  # ts_data passed directly
                tme = parse_tsdata_to_lists(ts_data_list[i])
            if len(tme) > 0:
                if all(len(this_tme) == 3 for this_tme in tme):
                    T, M, E = list(zip(*tme))
                    T = [float(el) for el in T]
                    M = [float(el) for el in M]
                    E = [float(el) for el in E]
                    features_already_known_list[i]["t"] = T
                    features_already_known_list[i]["m"] = M
                    features_already_known_list[i]["e"] = E
                elif all(len(this_tme) == 2 for this_tme in tme):
                    T, M = list(zip(*tme))
                    T = [float(el) for el in T]
                    M = [float(el) for el in M]
                    features_already_known_list[i]["t"] = T
                    features_already_known_list[i]["m"] = M
                else:
                    raise Exception("custom_feature_tools.py - "
                                    "docker_extract_features() - not all elements "
                                    "of tme are the same length.")


def make_tmp_dir():
    """
    """
    path_to_tmp_dir = os.path.join(cfg.PROJECT_PATH, "tmp",
                                   str(uuid.uuid4())[:10])
    os.makedirs(path_to_tmp_dir)
    return path_to_tmp_dir


def generate_random_str():
    """Generate random 10-character string using uuid.uuid4.
    """
    return str(uuid.uuid4())[:10]


def copy_data_to_tmp_dir(path_to_tmp_dir, script_fpath,
                         features_already_known_list):
    """
    """
    shutil.copy(script_fpath,
                os.path.join(path_to_tmp_dir, "custom_feature_defs.py"))
    with open(os.path.join(path_to_tmp_dir, "features_already_known_list.pkl"),
              "wb") as f:
        pickle.dump(features_already_known_list, f, protocol=2)
    # Create __init__.py file so that custom feats script can be imported
    open(os.path.join(path_to_tmp_dir, "__init__.py"), "w").close()
    return


def extract_feats_in_docker_container(container_name, path_to_tmp_dir):
    """
    """
    from docker import Client
    from . import run_in_docker_container as ridc
    tmp_data_dir = path_to_tmp_dir
    try:
        # Spin up Docker contain and extract custom feats
        # Instantiate Docker client
        client = Client(base_url='unix://var/run/docker.sock',
                        version='1.14')
        # Create container
        cont_id = client.create_container(
            image="mltsp/base_disco",
            command="python {}/run_script_in_container.py --{} --tmp_dir={}".format(
                cfg.PROJECT_PATH, "extract_custom_feats", tmp_data_dir),
            tty=True,
            volumes={cfg.PROJECT_PATH: ""})["Id"]
        # Start container
        client.start(cont_id,
                     binds={cfg.PROJECT_PATH: {"bind": cfg.PROJECT_PATH,
                                           "ro": True}})
        # Wait for process to complete
        client.wait(cont_id)
        stdout = client.logs(container=cont_id, stdout=True)
        stderr = client.logs(container=cont_id, stderr=True)
        if str(stderr).strip() != "" and stderr != b'':
            print("\n\ndocker container stderr:\n\n", str(stderr).strip(), "\n\n")
        # Copy pickled results data from Docker container to host
        ridc.docker_copy(client, cont_id, "/tmp/results_list_of_dict.pkl",
                         target=path_to_tmp_dir)
        print("/tmp/results_list_of_dict.pkl copied to host machine.")
        # Load pickled results data
        with open(os.path.join(path_to_tmp_dir, "results_list_of_dict.pkl"),
                  "rb") as f:
            results_list_of_dict = pickle.load(f)
    except:
        pass
    finally:
        # Kill and remove the container
        client.remove_container(container=cont_id, force=True)
        return results_list_of_dict


def remove_tmp_files(path_to_tmp_dir):
    """
    """
    # Remove tmp dir
    shutil.rmtree(path_to_tmp_dir, ignore_errors=True)
    for tmp_file in (os.path.join(cfg.TMP_CUSTOM_FEATS_FOLDER,
                                  "custom_feature_defs.py"),
                     os.path.join(cfg.TMP_CUSTOM_FEATS_FOLDER,
                                  "custom_feature_defs.pyc"),
                     os.path.join(cfg.TMP_CUSTOM_FEATS_FOLDER,
                                  "__init__.pyc")):
        try:
            os.remove(tmp_file)
        except Exception as e:
            print(e)

    return


def docker_extract_features(
        script_fpath, features_already_known_list=[{}],
        ts_datafile_paths=None, ts_data_list=None):
    """Extract custom features in a Docker container.

    Spins up a docker container in which custom script
    excecution/feature extraction is done inside. Resulting data are
    copied to host machine and returned as a dict.

    Parameters
    ----------
    script_fpath : str
        Path to script containing custom feature definitions.
    features_already_known_list : list of dict, optional
        List of dictionaries containing time series data (t,m,e) and
        any meta-features to be used in generating custom features.
        Defaults to []. NOTE: If omitted, or if "t" or "m" are not
        among contained dict keys, either (a) respective element of
        `ts_datafile_paths` or (b) `ts_data_list` (see below) MUST not
        be None, otherwise raises ValueError.
    ts_datafile_paths : list of str, optional
        List of paths to time-series CSV files. Defaults to None. NOTE:
        If None, either (a) corresponding element of
        `features_already_known_list` (see above) must contain "t"
        (time) and "m" (magnitude, or the measurement at each time)
        among its keys, OR (b) `ts_data_list` (see below) must be
        provided, otherwise raises ValueError.
    ts_data_list : list of list OR str, optional
        List of either (a) list of lists/tuples each containing t,m(,e)
        for each epoch, or (b) string containing equivalent comma-
        separated lines, each line being separated by a newline
        character ("\n"). Defaults to None. NOTE: If None, either
        `ts_datafile_paths` must not be None or "t" (time) and "m"
        (magnitude/measurement) must be among the keys of
        respective element of `features_already_known_list` (see
        above), otherwise raisesValueError.

    Returns
    -------
    list of dict
        List of dictionaries of all generated features.

    """
    if isinstance(features_already_known_list, dict):
        features_already_known_list = [features_already_known_list]
    add_tsdata_to_feats_known_dict(features_already_known_list,
                                   ts_datafile_paths, ts_data_list)
    container_name = generate_random_str()
    path_to_tmp_dir = make_tmp_dir()

    copy_data_to_tmp_dir(path_to_tmp_dir, script_fpath,
                         features_already_known_list)

    try:
        results_list_of_dict = extract_feats_in_docker_container(
            container_name, path_to_tmp_dir)
    except:
        raise
    finally:
        remove_tmp_files(path_to_tmp_dir)
    return results_list_of_dict


def assemble_test_data():
    """
    """
    features_already_known_list = []
    fname = os.path.join(cfg.SAMPLE_DATA_PATH, "dotastro_215153.dat")
    t, m, e = parse_csv_file(fname)
    features_already_known_list.append(
        {"t": t, "m": m, "e": e, "coords": [0, 0]})
    features_already_known_list.append(
        {"t": [1, 2, 3], "m": [50, 51, 52], "e": [0.3, 0.2, 0.4],
         "coords": [-11, -55]})
    features_already_known_list.append(
        {"t": [1], "m": [50], "e": [0.3], "coords": 2})
    return features_already_known_list


def verify_new_script(script_fpath, docker_container=False):
    """Test custom features script and return generated features.

    Performs test run on custom feature def script with trial time
    series data sets and returns list of dicts containing extracted
    features if successful, otherwise raises an exception.

    Parameters
    ----------
    script_fpath : str
        Path to custom feature definitions script.
    docker_container : bool, optional
        Boolean indicating whether function is being called from within
        a Docker container.

    Returns
    -------
    list of dict
        List of dictionaries of extracted features for each of the trial
        time-series data sets.

    """
    features_already_known_list = assemble_test_data()

    all_extracted_features_list = []
    if docker_images_available():
        print("Extracting features inside docker container...")
        all_extracted_features_list = docker_extract_features(
            script_fpath=script_fpath,
            features_already_known_list=features_already_known_list)
    else:
        print("Docker not installed - running custom features script could be "
              "unsafe. Skipping generation of custom features.")
        return []
    return all_extracted_features_list


def list_features_provided(script_fpath):
    """Parses script and returns a list of all features it provides.

    Parses decorator expression in custom feature definitions script,
    returning a list of all feature names generated by the various
    definitions in that script.

    Parameters
    ----------
    script_fpath : str
        Path to custom features definition script.

    Returns
    -------
    list of str
        List of feature names that the script will generate.

    """
    with open(script_fpath, "r") as f:
        all_lines = f.readlines()
    fnames_req_prov_dict = {}
    all_required_params = []
    all_provided_params = []
    for i in range(len(all_lines) - 1):
        if "@myFeature" in all_lines[i] and "def " in all_lines[i + 1]:
            reqs_provs_1 = parse(
                "@myFeature(requires={requires}, provides={provides})",
                all_lines[i].strip())
            func_name = parse(
                "def {funcname}({args}):", all_lines[i + 1].strip())
            fnames_req_prov_dict[func_name.named['funcname']] = {
                "requires": eval(reqs_provs_1.named["requires"]),
                "provides": eval(reqs_provs_1.named["provides"])}
            all_required_params = list(set(
                all_required_params +
                list(set(eval(reqs_provs_1.named["requires"])))))
            all_provided_params = list(set(
                all_provided_params +
                list(set(eval(reqs_provs_1.named["provides"])))))
    return all_provided_params


def generate_custom_features(
        custom_script_path, path_to_csv=None, features_already_known={},
        ts_data=None):
    """Generate custom features for provided TS data and script.

    Parameters
    ----------
    custom_script_path : str
        Path to custom features script.
    path_to_csv : str, optional
        Path to CSV file containing time-series data. Defaults to None.
        If None, ts_data (see below) must not be None, otherwise
        raises an Exception.
    features_already_known : dict, optional
        List of dicts containing any meta-features associated with
        provided time-series data. Defaults to [].
    ts_data : list OR tuple, optional
        List (or tuple) of lists (or tuples) containing time,
        measurement (and optionally associated error values) data.
        Defaults to None. If None, path_to_csv must not be None,
        otherwise raises an Exception.

    Returns
    -------
    list of dict
        List of dictionaries containing newly-generated features.

    """
    if path_to_csv:
        t, m, e = parse_csv_file(path_to_csv)
    elif ts_data:
        if len(ts_data[0]) == 3:
            t, m, e = list(zip(*ts_data))
        if len(ts_data[0]) == 2:
            t, m = list(zip(*ts_data))
    elif "t" not in features_already_known or "m" not in features_already_known:
        print("predict_class.predict:")
        print("path_to_csv:", path_to_csv)
        print("ts_data:", ts_data)
        raise Exception("Neither path_to_csv nor ts_data provided...")
    if "t" not in features_already_known:
        features_already_known['t'] = t
    if "m" not in features_already_known:
        features_already_known['m'] = m
    if e and len(e) == len(m) and "e" not in features_already_known:
        features_already_known['e'] = e

    if is_running_in_docker():
        all_new_features = execute_functions_in_order(
            features_already_known=features_already_known,
            script_fpath=custom_script_path)
    else:
        if docker_images_available():
            print("Generating custom features inside docker container...")
            all_new_features = docker_extract_features(
                script_fpath=custom_script_path,
                features_already_known_list=features_already_known)
        else:
            print("Generating custom features WITHOUT docker container...")
            all_new_features = execute_functions_in_order(
                features_already_known=features_already_known,
                script_fpath=custom_script_path)

    return all_new_features
