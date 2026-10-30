import streamlit as st
import psycopg2
import pandas as pd

# Page Configuration
st.set_page_config(page_title="Surfing Data Logger & Dashboard", layout="wide")


# Establish connection to Supabase using Streamlit secrets
@st.resource
def init_connection():
    return psycopg2.connect(st.secrets["postgres"]["connection_string"])


conn = init_connection()


# Helper function to run queries and return DataFrames
def run_query(query, params=None):
    with conn.cursor() as cur:
        cur.execute(query, params)
        try:
            data = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            return pd.DataFrame(data, columns=cols)
        except psycopg2.ProgrammingError:
            return pd.DataFrame()


def execute_commit(query, params=None):
    with conn.cursor() as cur:
        cur.execute(query, params)
        conn.commit()


st.title("🏄‍♂️ Surfing Competition Data Platform")

# Sidebar navigation
page = st.sidebar.selectbox("Navigation",
                            ["Log Wave & Manoeuvre", "View Heats & Scores", "Manage Lookups (Manoeuvres)"])

# -------------------------------------------------------------
# PAGE 1: LOG WAVES & MANOEUVRES
# -------------------------------------------------------------
if page == "Log Wave & Manoeuvre":
    st.header("Log a Surfer's Wave & Manoeuvres")

    # Fetch active heats joined with rounds and competitions
    heat_query = """
        SELECT 
            hs.heat_surfer_id,
            c.competition_name || ' -> ' || r.round_name || ' -> Heat ' || h.heat_number || ' (' || s.first_name || ' ' || s.last_name || ')' AS label
        FROM heat_surfer_table hs
        JOIN heat_table h ON hs.heat_id = h.heat_id
        JOIN round_table r ON h.round_id = r.round_id
        JOIN competition_table c ON r.competition_id = c.competition_id
        JOIN surfer_table s ON hs.surfer_id = s.surfer_id
        ORDER BY c.competition_start_date DESC;
    """
    heats_df = run_query(heat_query)

    if heats_df.empty:
        st.warning(
            "No heat rosters found in the database yet. Please add competitions, heats, and assign surfers first.")
    else:
        with st.form("wave_form"):
            st.subheader("1. Wave Details")
            selected_heat_surfer = st.selectbox("Select Competition / Heat / Surfer", heats_df["label"])
            heat_surfer_id = int(heats_df.loc[heats_df["label"] == selected_heat_surfer, "heat_surfer_id"].values[0])

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                wave_number = st.number_input("Wave Number", min_value=1, step=1)
            with col2:
                score = st.number_input("Wave Score", min_value=0.0, max_value=10.0, step=0.1)
            with col3:
                priority_status = st.checkbox("Had Priority?")
            with col4:
                front_back_side = st.selectbox("Approach", ["", "frontside", "backside"])

            st.subheader("2. Manoeuvre Details (Optional)")

            # Fetch manoeuvre types for dropdown
            m_types_df = run_query("SELECT manoeuvre_type_id, name, category FROM manoeuvre_type_table")

            has_manoeuvre = st.checkbox("Add a manoeuvre to this wave?")

            manoeuvre_type_id = None
            completion = None
            location = None
            aerial_grab = None
            aerial_landing = None
            barrel_exit = None

            if has_manoeuvre and not m_types_df.empty:
                m_choice = st.selectbox("Manoeuvre Type", m_types_df["name"] + " (" + m_types_df["category"] + ")")
                manoeuvre_type_id = int(m_types_df.loc[m_types_df["name"] + " (" + m_types_df[
                    "category"] + ")" == m_choice, "manoeuvre_type_id"].values[0])

                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    completion = st.selectbox("Completion", ["complete", "incomplete"])
                    location = st.selectbox("Location", ["", "pocket", "lip", "shoulder", "close-out"])
                with col_m2:
                    aerial_grab = st.selectbox("Aerial Grab",
                                               ["", "no grab", "frontside/indy", "slob", "lien", "mute", "stale"])
                with col_m3:
                    aerial_landing = st.selectbox("Aerial Landing", ["", "lip", "whitewash", "mid-face", "flats"])
                    barrel_exit = st.selectbox("Barrel Exit", ["", "clean", "chandelier", "through the lip"])

            submitted = st.form_submit_button("Save Wave & Manoeuvre")

            if submitted:
                # Insert Wave
                wave_insert_query = """
                    INSERT INTO wave_table (heat_surfer_id, wave_number, score, priority_status, front_back_side)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING wave_id;
                """
                with conn.cursor() as cur:
                    cur.execute(wave_insert_query,
                                (heat_surfer_id, wave_number, score, priority_status, front_back_side))
                    wave_id = cur.fetchone()[0]

                    # Insert Manoeuvre if selected
                    if has_manoeuvre and manoeuvre_type_id:
                        manoeuvre_insert_query = """
                            INSERT INTO manoeuvre_table (wave_id, manoeuvre_type_id, completion, location, aerial_grab, aerial_landing, barrel_exit)
                            VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """
                        cur.execute(manoeuvre_insert_query,
                                    (wave_id, manoeuvre_type_id, completion, location, aerial_grab, aerial_landing,
                                     barrel_exit))

                    conn.commit()
                st.success("Successfully logged wave and performance data!")

# -------------------------------------------------------------
# PAGE 2: VIEW HEATS & SCORES
# -------------------------------------------------------------
elif page == "View Heats & Scores":
    st.header("Competition Wave Analytics & Logs")

    query = """
        SELECT 
            c.competition_name,
            r.round_name,
            h.heat_number,
            s.first_name || ' ' || s.last_name AS surfer_name,
            w.wave_number,
            w.score,
            w.priority_status,
            w.front_back_side,
            mt.name AS manoeuvre_name,
            mt.category AS manoeuvre_category,
            m.completion,
            m.aerial_grab
        FROM wave_table w
        JOIN heat_surfer_table hs ON w.heat_surfer_id = hs.heat_surfer_id
        JOIN surfer_table s ON hs.surfer_id = s.surfer_id
        JOIN heat_table h ON hs.heat_id = h.heat_id
        JOIN round_table r ON h.round_id = r.round_id
        JOIN competition_table c ON r.competition_id = c.competition_id
        LEFT JOIN manoeuvre_table m ON w.wave_id = m.wave_id
        LEFT JOIN manoeuvre_type_table mt ON m.manoeuvre_type_id = mt.manoeuvre_type_id
        ORDER BY w.wave_id DESC;
    """
    df = run_query(query)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No waves logged yet.")

# -------------------------------------------------------------
# PAGE 3: MANAGE LOOKUPS
# -------------------------------------------------------------
elif page == "Manage Lookups (Manoeuvres)":
    st.header("Manage Manoeuvre Types Library")

    with st.form("add_manoeuvre_type"):
        st.subheader("Add New Manoeuvre Category/Type")
        new_name = st.text_input("Manoeuvre Name (e.g., Air Reverse, Cutback)")
        new_cat = st.selectbox("Category", ["air", "turn", "tube", "fin-throw"])

        m_submit = st.form_submit_button("Add Manoeuvre Type")
        if m_submit and new_name:
            execute_commit(
                "INSERT INTO manoeuvre_type_table (name, category) VALUES (%s, %s);",
                (new_name, new_cat)
            )
            st.success(f"Added '{new_name}' to the manoeuvre library!")

    st.subheader("Current Manoeuvre Types")
    m_df = run_query("SELECT * FROM manoeuvre_type_table ORDER BY category, name;")
    st.dataframe(m_df, use_container_width=True)