# Create your Oracle Cloud computer: a beginner's walkthrough

English | [简体中文](OCI_ARM.zh-CN.md) | [Back to the setup guide](SETUP.md)

This walkthrough takes you from an Oracle account to a connected Ubuntu computer.
Oracle calls that computer an **instance** or **virtual machine (VM)**. It runs in
Oracle's data center, so your laptop does not have to stay on while Auto Quant runs.
You do not need to know how to program.

**Do these steps on your own computer.** You will use your browser first, then a
terminal: a window where you paste commands. No trading starts in this walkthrough.

The screenshots below come from Oracle and Canonical (the company behind Ubuntu).
They load from those companies' websites and need an Internet connection. Click a
screenshot to enlarge it. These are official tutorial examples, not screenshots of
your account; names, dates and layouts may differ. Follow the values written in
this guide. Instructions checked on **2026-10-11**.

- [1. Create an Oracle account](#oci-account)
- [2. Create its network](#oci-network)
- [3. Allow your computer to connect](#oci-firewall)
- [4. Create the Ubuntu instance and save its key](#oci-instance)
- [5. Connect to Ubuntu](#oci-connect)
- [6. Check it is ready](#oci-check)
- [If something goes wrong](#oci-help)

<a id="oci-account"></a>
## 1. Create an Oracle account

**Where: your computer's web browser.** If you already have an OCI account, sign in
at [Oracle Cloud](https://cloud.oracle.com/) and go to step 2.

Have your email, phone and payment card ready. Oracle may ask for these to verify
your identity. Read the charges and terms shown to you; creating this account is
separate from your Auto Quant subscription. Free trial credit is not a guarantee
that every resource you select stays free. See [Oracle's Free Tier explanation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

1. Open [Oracle's signup page](https://signup.oraclecloud.com/).
2. Enter your country, name and email. Complete the human-verification question,
   then click **Verify my email**.
3. Open the email from Oracle and follow its verification link.

[![Oracle signup form: country, name, email and human verification](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI4.png)](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI4.png)

*Screenshot: Oracle's [account signup tutorial](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/). Enter your own details.*

4. Create your password. Record the **Cloud Account Name**, which identifies your
   Oracle account when signing in.
5. Choose your **Home Region**, the geographic location for this setup. Choose
   carefully: Oracle says it cannot be changed after signup. Always Free compute
   must be created in that home region; availability still depends on capacity.
6. Complete the address, phone and payment verification requested by Oracle,
   review the agreement, then submit the registration.
7. Wait for the account-ready email. Open [Oracle Cloud](https://cloud.oracle.com/),
   enter your Cloud Account Name, and complete sign-in, including any security
   verification Oracle requests. [Oracle's signup instructions](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm)

[![Oracle account setup: Cloud Account Name and Home Region](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI11.png)](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/images/Getting-Started-OCI11.png)

*Screenshot: Oracle's [signup tutorial](https://docs.oracle.com/en/learn/get-started-with-oci-and-oci-console/). The Netherlands shown in the example is not a required location.*

**You are ready when:** you can see the Oracle Cloud Console, the website used to
manage your cloud computer. Keep your chosen home region selected at the top.

<a id="oci-network"></a>
## 2. Create a network for Auto Quant

**Where: Oracle Cloud Console in your browser.** A **VCN** is the network your
cloud computer uses. A **compartment** is a folder for Oracle resources. In a new
personal account, use your account's **root** compartment throughout this guide.

1. Open the top-left navigation menu **☰ → Networking → Virtual cloud networks**.
2. Select **Start VCN Wizard**. In some layouts it is under **Actions**.
3. Select **VCN with Internet Connectivity**, then start the wizard.

[![Oracle VCN wizard with the Internet Connectivity option](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/images/create_vcn_wizard_start.png)](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/images/create_vcn_wizard_start.png)

*Screenshot: Oracle's [VCN tutorial](https://docs.oracle.com/en/applications/peoplesoft/cloud-manager/tutorial-create-vcn-console/index.html). Only the network-creation part applies here.*

4. Name the network **auto-quant-network**. Select the same root compartment.
5. Keep the proposed network address ranges and DNS setting. Leave IPv6 off for
   this walkthrough. You do not need to calculate network addresses.
6. Review the resources and any displayed charges, then select **Create**.
7. When finished, select **View Virtual Cloud Network**. Note the subnet whose
   name contains **public**; use it for the instance in step 4.

The wizard supplies the route to the Internet. A private subnet alone will not
let your laptop connect using the instructions below. [Oracle's current network wizard instructions](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/quickstartnetworking.htm)

**You are ready when:** the network exists and you can open its public subnet.

<a id="oci-firewall"></a>
## 3. Allow only your computer to connect

**Where: your browser.** A **security list** is a list of allowed connections.
SSH, the connection used to control Ubuntu, uses **port 22**.

1. In another browser tab, search **what is my IPv4 address**. Copy the result
   with four groups of numbers. This is your home/office Internet address, not
   the future cloud computer's address.
2. Return to **auto-quant-network → Subnets → the public subnet → Security Lists**.
   Open its security list and find **Ingress Rules** (incoming connections).
3. If a TCP rule already allows destination port **22**, edit that rule. Otherwise,
   add one using this table. Do not leave another rule allowing port 22 from
   everyone; a narrower rule does not override a broader one.

| Field | Value |
| --- | --- |
| Stateless | Unchecked |
| Source Type | CIDR |
| Source CIDR | Your home/office IPv4 address followed by `/32` |
| IP Protocol | TCP |
| Source Port Range | All, or leave blank if the form uses blank for All |
| Destination Port Range | `22` |
| Description | My computer SSH |

For example, if your address were `203.0.113.10`, you would enter
`203.0.113.10/32`. **That is an example; use your own address.** `/32` means only
that one address. `0.0.0.0/0` means everyone.

Keep the existing ICMP network rules and the default **Egress** (outgoing) rule.
Do not add incoming rules for **4001, 4002 or 5901**, or an incoming “allow all”
rule. Gateway and the remote desktop will use a private connection instead.
This is a new network dedicated to Auto Quant; if you are reusing a shared network,
ask its administrator to check all attached security lists and network security
groups before changing rules. [Oracle security-list behavior](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)

**You are ready when:** incoming SSH is limited to your address. If you change
Wi-Fi, enable a VPN or your provider changes your address, update this rule before
trying to reconnect. Leave the Ubuntu firewall in place.

<a id="oci-instance"></a>
## 4. Create your Ubuntu instance

**Where: Oracle Cloud Console in your browser.**

Open **☰ → Compute → Instances → Create instance**. The form may be one long
page or several pages with **Next** buttons. Complete the sections below before
pressing the final **Create** button. [Oracle's instance-creation instructions](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm)

[![Oracle Instances page showing the Create Instance button](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/014.png)](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/014.png)

*Screenshot: Oracle's [OCI basics tutorial](https://docs.oracle.com/en/learn/oci-basics-tutorial/). Your instance list will differ.*

### Name, image and shape

An **image** is the operating system to install. A **shape** is the type and size
of the cloud computer. For this Auto Quant package, use these values:

| Setting | Choose |
| --- | --- |
| Name | `auto-quant` |
| Compartment | The same root compartment as the network |
| Placement | An available domain in your selected region; keep other defaults |
| Capacity type | On-demand, not preemptible |
| Image | **Canonical Ubuntu 24.04 LTS**, **ARM64 / aarch64** |
| Shape | **Ampere → VM.Standard.A1.Flex** |
| OCPUs | **2** |
| Memory | **8 GB** |

In **Image and shape**, use **Change image → Ubuntu**, then choose 24.04 and its
ARM64/aarch64 variant. Prefer the full image over Minimal when offered. Use
**Change shape** to choose Ampere A1. Recheck both selections afterward: some
image choices can change the available shapes. This package needs Ubuntu 24.04
and ARM64, even if an example screenshot shows another version.
[Canonical's Ubuntu image selector guide](https://ubuntu.com/docs/oracle/oracle-how-to/find-ubuntu-images/)

[![Canonical's screenshot of the Ubuntu image selection panel in OCI](https://ubuntu.com/docs/oracle/_images/1_latest_ubuntu_image.png)](https://ubuntu.com/docs/oracle/_images/1_latest_ubuntu_image.png)

*Screenshot: Canonical's [image guide](https://ubuntu.com/docs/oracle/oracle-how-to/find-ubuntu-images/). Choose **24.04 ARM64/aarch64** for Auto Quant, regardless of the example's selected release.*

Two OCPUs and 8 GB are a starting allocation for Gateway and its desktop, not a
tested minimum or a promise of free service. Check your own available allowance,
other resources and the cost estimate. If A1 has no capacity, try another
availability domain offered within your region or retry later. An AMD/Intel
instance is not a substitute for this ARM64 package.

### Network and SSH key

| Setting | Choose |
| --- | --- |
| Virtual cloud network | `auto-quant-network` |
| Subnet | The **public** subnet created in step 2 |
| Assign a public IPv4 address | **Yes / enabled** |
| Network security groups | Leave unselected for this dedicated-network walkthrough |
| Add SSH keys | **Generate a key pair for me** |

An **SSH key** is a small file that unlocks access to your Ubuntu computer.
Click **Download private key** and **Download public key** before leaving this
page. Older layouts call these **Save Private Key** and **Save Public Key**.

[![Oracle's SSH key section with buttons to save the private and public keys](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/021.png)](https://docs.oracle.com/en/learn/oci-basics-tutorial/img/021.png)

*Screenshot: Oracle's [OCI basics tutorial](https://docs.oracle.com/en/learn/oci-basics-tutorial/). The private key is the one used to connect.*

On **your own computer**, find the downloaded **private** key (not the `.pub`
file) and rename it **auto-quant.key**. Keep it in your **Downloads** folder for
this walkthrough and keep a private backup. Do not send it to Auto Quant, Discord
or anyone else. On Windows, show file-name extensions so it does not accidentally
become `auto-quant.key.key` or `auto-quant.key.txt`.

### Storage and final review

Keep the standard boot disk size/performance and other settings; no extra disk
is needed for this walkthrough. Review any estimated charges. Before **Create**,
confirm **Ubuntu 24.04**, **A1 ARM64**, **2 OCPUs / 8 GB**, a **public subnet and
public IPv4**, and that you have saved the private key.

Click **Create**, then wait for the instance status to become **Running**. On
its details page, copy **Public IPv4 address** (sometimes under **Networking**
or the primary network interface). Do not copy its private address or its OCID,
which is a long resource identifier. [Oracle's first-instance tutorial](https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm)

**You are ready when:** the instance says Running and you have both its public
IPv4 address and the private key file on your computer.

<a id="oci-connect"></a>
## 5. Connect to Ubuntu for the first time

**Where: a terminal on your own computer.**

- **Windows 10/11:** open Start, type **PowerShell**, and open it.
- **Mac:** press **Command + Space**, type **Terminal**, and press Enter.
- **Linux:** open your Terminal application.

Paste one line at a time and press Enter. Move into your Downloads folder:

```bash
cd ~/Downloads
```

If you use a different download folder, open the terminal in that folder instead.
The folder must contain **auto-quant.key**. Mac/Linux users should also run the
following line to make the key readable only by themselves. **Skip this line in
Windows PowerShell.**

```bash
chmod 400 auto-quant.key
```

Now connect. **Replace `YOUR_OCI_PUBLIC_IP` with the instance's public IPv4 address
from step 4.** Keep everything else, including `ubuntu@`, as written.

```bash
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

The first connection asks whether you trust the server. Check that the address
is the one you copied from OCI; type `yes` and press Enter for this new instance.
For a later “host identification has changed” warning, stop and investigate rather
than deleting the warning automatically. The SSH key supplies your login; do not
enter your Oracle or IBKR password if SSH unexpectedly asks for a password.
[Oracle's Linux connection instructions](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm)

**You are ready when:** the prompt changes to something like `ubuntu@auto-quant:~$`.
This terminal now controls the **cloud computer**, not your laptop. Keep it open;
we will call it **Window A — Ubuntu** in the main guide.

<a id="oci-check"></a>
## 6. Check the computer is ready

**Where: Window A — Ubuntu.** Paste these lines one at a time:

```bash
uname -m
. /etc/os-release
printf '%s %s\n' "$ID" "$VERSION_ID"
python3.12 --version
timedatectl status
```

| Check | What you should see |
| --- | --- |
| Computer type | `aarch64` |
| Operating system | `ubuntu 24.04` |
| Python | `Python 3.12.x`, with a number in place of x |
| Clock | `System clock synchronized: yes` |

The `. /etc/os-release` line normally prints nothing. If clock synchronization
says no, run this, wait briefly, then repeat `timedatectl status`:

```bash
sudo timedatectl set-ntp true
```

If the other values differ, stop and check the instance image/shape before
installing. Do not change the system's default Python to another version.

**Finished:** return to [setup step 3 — transfer the download](SETUP.md#transfer).
You will keep Ubuntu connected in Window A and open a second terminal on your
own computer to transfer the files.

<a id="oci-help"></a>
## If something goes wrong

| What you see | What to do |
| --- | --- |
| Oracle rejects signup/payment verification | Check the details with Oracle signup support. Auto Quant cannot activate the Oracle account for you. |
| “Out of capacity” | Try another available domain for A1 in the same region or retry later; keep the required ARM64 shape. |
| No public IPv4 address | Check the instance uses the public subnet and has public IPv4 assignment enabled. A `10.x.x.x` address is private. |
| SSH times out | Confirm Running, the public IP, public subnet, and your current home/office address in the port-22 rule. VPN/Wi-Fi changes can change that address. |
| “Identity file … not accessible” | Check that this terminal is in Downloads and the private file is named exactly `auto-quant.key`. |
| “Permission denied (publickey)” | Use username `ubuntu` and the private key downloaded for this instance, not the `.pub` file. |
| “UNPROTECTED PRIVATE KEY FILE” | Mac/Linux: apply the `chmod` line above. Windows: follow the permission steps below. |
| Windows says `ssh` is not recognized | Install **OpenSSH Client** from Windows **Optional features**, then reopen PowerShell. [Microsoft's instructions](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse) |
| Ubuntu verification shows `x86_64` or a different release | The image/shape is wrong for this download. Correct it before installing Auto Quant. |

For a **Windows key-permission warning**, right-click `auto-quant.key` →
**Properties → Security → Advanced**. Confirm your Windows account is the owner.
Disable inheritance and remove inherited permissions; add your own Windows
account with **Read** permission, and remove entries granting other ordinary
users access. Apply, then retry SSH. If unsure which account is yours, get help
before changing permissions; do not share the key file.

When asking for help, send the step number and the error text. Hide passwords,
private keys, relay tokens and one-time linking codes.
